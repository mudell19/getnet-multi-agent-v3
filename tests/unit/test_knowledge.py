from getnet_multi_agent.agents import knowledge
from getnet_multi_agent.contracts import LLMResult, Source, Step, TraceCall
from tests.conftest import FakeLLM
from tests.integration.conftest import FakeRetriever


def test_fr005_no_answer_is_ungrounded():
    r = knowledge.run_rag(FakeLLM({"knowledge_rag": "NO_ANSWER"}), FakeRetriever(),
                          Step(agent="knowledge", source="rag", query="q"), "en", "T")
    assert r.observation.status == "ungrounded"
    r = knowledge.run_rag(FakeLLM(), FakeRetriever([]),
                          Step(agent="knowledge", source="rag", query="q"), "en", "T")
    assert r.observation.status == "ungrounded"


def test_fr005_grounded_answer_cites_matching_page():
    llm = FakeLLM({"knowledge_rag": "Run the communication test: press F, 60, option 2 "
                                    "manutenção, option 1 teste de comunicação."})
    r = knowledge.run_rag(llm, FakeRetriever(), Step(agent="knowledge", source="rag", query="q"),
                          "en", "T")
    assert r.observation.status == "answered"
    assert r.sources[0].url.endswith("/duvidas/algar")


def test_fr021_web_uses_search_without_tools():
    res = LLMResult(text="EUR 1 = R$ 6,10 at 10:00, source X.", usage=TraceCall(purpose="w"),
                    sources=[Source(title="x.com", url="https://vertexaisearch/x")])
    llm = FakeLLM({"knowledge_web": res})
    r = knowledge.run_web(llm, Step(agent="knowledge", source="web", query="euro?"), "en", "T")
    assert llm.calls[0]["search"] is True and llm.calls[0]["tools"] is None
    assert r.sources[0].title == "x.com"
