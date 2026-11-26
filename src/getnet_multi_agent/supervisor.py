"""Bounded supervisor loop: plan, execute steps, critic replans, synthesis, Personality."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from getnet_multi_agent.agents import critic, knowledge, personality, planner, support, synthesis
from getnet_multi_agent.agents import escalation as esc
from getnet_multi_agent.contracts import (
    LLM,
    AgentResult,
    BudgetExceeded,
    Lang,
    LLMUnavailable,
    Observation,
    Plan,
    PlanRevision,
    Principal,
    RunCheckpoint,
    Source,
    Step,
    Trace,
    TraceCall,
)
from getnet_multi_agent.core import metrics
from getnet_multi_agent.core.context import current
from getnet_multi_agent.core.logging import log_event
from getnet_multi_agent.core.settings import get_settings
from getnet_multi_agent.format.lang import detect_language
from getnet_multi_agent.format.quality import check_answer, fix_answer, localize_amounts
from getnet_multi_agent.security import dlp
from getnet_multi_agent.security.guardrails import REFUSAL_TEXTS

GLOBAL_CAVEAT = {
    "en": "Information from Getnet's global site may differ for Brazil.",
    "pt": "As informações do site global da Getnet podem ser diferentes no Brasil.",
}
_TOK = re.compile(r"\w+", re.UNICODE)


@dataclass
class RunResult:
    answer: str
    status: str
    route: str
    language: Lang
    refusal_reason: str | None = None
    sources: list[Source] = field(default_factory=list)
    ticket_id: str | None = None
    trace: Trace = field(default_factory=Trace)


def excerpt(text: str, answer: str, size: int = 300) -> str:
    """The ~300-char window of the chunk sharing the most words and numbers with the answer."""
    if len(text) <= size:
        return text
    ans = {t for t in _TOK.findall(answer.lower()) if len(t) > 2 or t.isdigit()}
    words = list(re.finditer(r"\S+", text))
    best, best_start = -1, 0
    for i, m in enumerate(words):
        window = text[m.start(): m.start() + size]
        score = len(ans & {t for t in _TOK.findall(window.lower())})
        if score > best:
            best, best_start = score, m.start()
        if i > 400:
            break
    return text[best_start: best_start + size]


class Supervisor:
    def __init__(self, llm: LLM, retriever_factory, db):
        self.llm = llm
        self.retriever_factory = retriever_factory
        self.db = db

    # --------------------------------------------------------------- steps
    def _run_step(self, step: Step, principal: Principal, lang: Lang, today: str) -> AgentResult:
        try:
            if step.agent == "support":
                return support.run(self.llm, step, principal, lang, today)
            if step.source == "web":
                return knowledge.run_web(self.llm, step, lang, today)
            return knowledge.run_rag(self.llm, self.retriever_factory(), step, lang, today)
        except (BudgetExceeded, LLMUnavailable):
            raise
        except Exception as e:  # a tool or retrieval failure escalates that part only
            log_event("step_failed", level="error", step=step.label(), error=type(e).__name__)
            return AgentResult(observation=Observation(step=step, status="failed"))

    # --------------------------------------------------------------- main loop
    def run(self, message: str, principal: Principal, conversation_id: str, request_id: str,
            summary: str, turns: list[dict], today: str) -> RunResult:
        s = get_settings()
        trace = Trace()
        calls: list[TraceCall] = []
        lang: Lang = detect_language(message)
        plan = Plan(standalone=message, language=lang)
        executed: list[Observation] = []
        sources: list[Source] = []
        escalation_reason: str | None = None
        try:
            plan, usage = planner.plan(self.llm, message, summary, turns, today)
            calls.append(usage)
            lang = plan.language
            trace.plan_revisions.append(PlanRevision(
                iteration=0, action="initial", reason="router plan: " + " > ".join(
                    st.label() for st in plan.steps) if plan.steps else "router plan: no steps"))
            if plan.refusal_reason:
                return self._finish_refusal(plan, lang, trace, calls)
            if plan.escalate:
                escalation_reason = "human_requested"
            else:
                pending = list(plan.steps) or [Step(agent="knowledge", source="rag",
                                                    query=plan.standalone)]
                retried: set[str] = set()
                for iteration in range(1, s.MAX_SUPERVISOR_ITERATIONS + 1):
                    while pending:
                        step = pending.pop(0)
                        r = self._run_step(step, principal, lang, today)
                        calls.extend(r.calls)
                        executed.append(r.observation)
                        sources.extend(x for x in r.sources if x.url not in {y.url for y in sources})
                    actions = critic.rules(executed, pending, retried, lang, plan.standalone)
                    for action, step, reason in actions:
                        trace.plan_revisions.append(PlanRevision(
                            iteration=iteration, action=action, step=step, reason=reason))
                        metrics.REPLANS.inc()
                        if action == "drop":
                            pending = [p for p in pending if p is not step]
                        else:
                            if action == "retry":
                                for o in executed:
                                    if o.status == "ungrounded" and o.step.source == step.source:
                                        o.facts["superseded"] = True
                            pending.append(step)
                    if pending:
                        continue
                    answered = [o.answer for o in executed if o.status == "answered"]
                    if not answered or iteration == s.MAX_SUPERVISOR_ITERATIONS:
                        break
                    verdict, usage = critic.check(self.llm, plan.standalone, answered, today)
                    calls.append(usage)
                    trace.critic_notes.append(
                        f"complete={verdict.complete}; unanswered={verdict.unanswered}; "
                        f"{verdict.notes}")
                    if verdict.complete or not verdict.unanswered:
                        break
                    part = verdict.unanswered[0]
                    done = {o.step.query for o in executed}
                    if part in done:
                        break
                    step = Step(agent="knowledge", source="rag", query=part,
                                reason="critic: part not answered")
                    trace.plan_revisions.append(PlanRevision(
                        iteration=iteration, action="add", step=step,
                        reason=f"critic found an unanswered part: {part}"))
                    metrics.REPLANS.inc()
                    pending.append(step)
        except BudgetExceeded:
            escalation_reason = "budget_exceeded"
        except LLMUnavailable:
            escalation_reason = "llm_failure"
        trace.observations = executed
        live = [o for o in executed if not o.facts.get("superseded")]
        answered = [o for o in live if o.status in ("answered", "not_found") and o.answer]
        unanswered = [o for o in live if o not in answered]
        if escalation_reason is None and unanswered:
            escalation_reason = ("missing_grounding" if any(o.status == "ungrounded"
                                                            for o in unanswered) else "tool_failure")
        return self._finish(plan, lang, message, conversation_id, request_id, today, trace, calls,
                            answered, unanswered, sources, escalation_reason, principal)

    # --------------------------------------------------------------- endings
    def _totals(self, trace: Trace, calls: list[TraceCall]) -> None:
        trace.calls = calls
        trace.total_tokens = sum(c.prompt_tokens + c.output_tokens + c.thinking_tokens
                                 for c in calls)
        trace.total_cost_usd = round(sum(c.cost_usd for c in calls), 6)
        ctx = current()
        if ctx is not None:
            trace.total_tokens = max(trace.total_tokens, ctx.tokens)

    def _finish_refusal(self, plan: Plan, lang: Lang, trace: Trace, calls) -> RunResult:
        self._totals(trace, calls)
        reason = plan.refusal_reason
        metrics.REFUSALS.labels(reason=reason).inc()
        return RunResult(answer=REFUSAL_TEXTS[reason][lang], status="refused", route="refusal",
                         language=lang, refusal_reason=reason, trace=trace)

    def _finish(self, plan, lang, message, conversation_id, request_id, today, trace, calls,
                answered, unanswered, sources, escalation_reason, principal) -> RunResult:
        draft = ""
        if answered:
            try:
                draft, usage = synthesis.merge(self.llm, plan.standalone,
                                               [o.answer for o in answered], lang, today)
                if usage:
                    calls.append(usage)
            except (BudgetExceeded, LLMUnavailable):
                draft = "\n\n".join(o.answer for o in answered)
                escalation_reason = escalation_reason or "llm_failure"
        ticket_id = None
        if escalation_reason:
            cp = RunCheckpoint(plan=plan, revisions=trace.plan_revisions, observations=trace.observations,
                               draft=draft, language=lang,
                               pending_parts=[o.step.query for o in unanswered] or [plan.standalone])
            ticket_id = esc.escalate(self.db, conversation_id, request_id, cp, escalation_reason,
                                     message)
            metrics.ESCALATIONS.labels(reason=escalation_reason).inc()
            log_event("escalated", reason=escalation_reason, ticket_id=ticket_id)
        answer = draft
        if draft:
            try:
                answer, viol, usage = personality.rewrite(self.llm, plan.standalone, draft, lang,
                                                          today)
                if usage:
                    calls.append(usage)
            except BudgetExceeded:
                viol = ["personality_skipped_budget"]
            trace.quality_violations.extend(viol)
        if ticket_id:
            note = esc.message(lang, ticket_id, partial=bool(answered))
            answer = f"{answer}\n\n{note}" if answer else note
        answer, fixed = fix_answer(answer)
        answer = localize_amounts(answer, lang)
        remaining = check_answer(answer, lang)
        leaks = dlp.check_final(answer, principal)
        if leaks:
            answer = dlp.mask(answer)
            for mid in dlp.other_merchant_ids(answer, principal.sub):
                answer = re.sub(re.escape(mid), "[redacted]", answer, flags=re.I)
            trace.quality_violations.extend(f"dlp_{x}" for x in leaks)
        for v in fixed + remaining:
            metrics.QUALITY_VIOLATIONS.labels(rule=v).inc()
        trace.quality_violations.extend(fixed + remaining)
        if trace.quality_violations:
            log_event("quality_violations", violations=trace.quality_violations)
        if answered and any("getnet.net" in src.url for src in sources):
            answer = f"{answer}\n\n{GLOBAL_CAVEAT[lang]}"
        answer_text = answer
        for o in trace.observations:
            for ev in o.evidence:
                if ev.kind in ("rag", "tool"):
                    ev.excerpt = excerpt(ev.excerpt, answer_text)
        self._totals(trace, calls)
        route = ("escalation" if ticket_id else
                 ">".join(dict.fromkeys(o.step.label() for o in answered)) or "knowledge:rag")
        return RunResult(answer=answer, status="awaiting_human" if ticket_id else "answered",
                         route=route, language=lang, sources=sources if answered else [],
                         ticket_id=ticket_id, trace=trace)
