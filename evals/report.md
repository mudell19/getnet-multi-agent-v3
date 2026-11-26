# Eval report

Run mode: rerun failures: every case run once; each failing case rerun 3 more times; final outcome is the majority of 4 runs (a tie fails); each row shows one run matching the final outcome

Cases: 40, passed: 30, chat requests: 42

## Metrics

| Metric | Value | Threshold |
|---|---|---|
| routing_accuracy | 0.947 | 0.900 |
| deterministic_quality | 0.946 | 1.000 |
| correct_refusal_rate | 1.000 | 1.000 |
| citation_rate | 1.000 | 0.950 |
| source_match_rate | 0.750 | 0.800 |
| must_mention_pass_rate | 0.860 | 0.900 |
| must_not_pass_rate | 0.967 | n/a |
| judge_correctness | 4.552 | 4.000 |
| judge_groundedness | 4.345 | 4.000 |
| judge_relevance | 4.724 | 4.000 |
| judge_helpfulness | 4.621 | 4.000 |
| judge_clarity | 4.897 | 4.000 |

Latency p50 8655 ms, p95 20058 ms.

Cost: system USD 0.23337, judge USD 0.14386, total USD 0.37724, per chat request USD 0.00556.

Correct refusal rate includes the authorization cases (401 and 403).

## By language

| Lang | Cases | Passed | Routing accuracy |
|---|---|---|---|
| en | 25 | 20 | 1.000 |
| pt | 15 | 10 | 0.867 |

## Thresholds (FR-067)

- MISSED: deterministic_quality 0.946 < 1.0
- MISSED: source_match_rate 0.750 < 0.8
- MISSED: must_mention_pass_rate 0.860 < 0.9

## Flaky cases (mixed outcomes across runs)

- official-03-deposit: passed 3 of 4
- official-05-offline: passed 3 of 4
- pt-pix-account: passed 2 of 4
- support-sales-yesterday-en: passed 2 of 4

## Five lowest-clarity answers

### memory-other-terminal-pt (clarity 3)

```text
Para verificar a conexão, desligue e ligue a maquininha Get Clássica e realize o teste de comunicação seguindo o passo a passo:

1. Com a máquina desligada, abra a tampa traseira;
2. Insira o chip no local indicado (SIM1 ou SIM2), com a parte metálica voltada para baixo;
3. Feche a tampa, ligue a máquina e aguarde a indicação de rede (2G ou 3G);
4. Pressione o botão função (F, # ou o da sua máquina);
5. Pressione 60;
6. Selecione a opção 2 (manutenção);
7. Selecione a opção 1 (teste de comunicação).
```

### memory-smart-price (clarity 4)

```text
The monthly cost for the Get Smart card machine is R$ 129.90 per month if you do not reach the required sales volume. You can get rent exemption and use it for free if you sell above R$ 40,000 por mês or above R$ 80,000 por mês. Keep in mind that Voucher (VA/VR) and Crediário transactions do not count towards the sales volume for this exemption.

Information from Getnet's global site may differ for Brazil.
```

### official-01-machines (clarity 5)

```text
Get Clássica is a reliable POS for accepting chip card, magnetic stripe, contactless, and mobile payments anywhere in your business. Get Smart is an Android POS that brings business management directly to the terminal, letting you track inventory, take orders, close bills, issue tax receipts, and integrate APIs. The monthly fee is R$ 79.90 per month for Get Clássica and R$ 129.90 per month for Get Smart, which become free with monthly sales over R$ 20,000 and R$ 40,000, respectively.

Information from Getnet's global site may differ for Brazil.
```

### official-02-weather (clarity 5)

```text
The weather forecast for Porto Alegre tomorrow, November 27, 2026, shows a minimum temperature of 17°C and a maximum temperature of 26°C. There is also a 40% chance of rain, according to Weather Underground.
```

### official-03-deposit (clarity 5)

```text
The total of R$ 1,739.90 from yesterday's sales will be deposited into your Getnet account on Friday, 27 Nov 2026. This amount includes R$ 1,250.00 from credit sales and R$ 489.90 from debit sales. You do not need to take any action, as your funds are credited automatically two business days after the sale date.
```

## Failures

| Case | Lang | Route | Failures |
|---|---|---|---|
| official-01-machines | en | knowledge:rag | quality: unformatted_amount; judge must_mention: Get Smart is an Android machine with stock control and cashier features integrated, and it accepts vouchers and apps |
| official-10-payment-link | en | knowledge:rag | source https://site.getnet.com.br/duvidas/link-de-pagamento not in sources |
| pt-pix-account | pt | knowledge:rag | source https://site.getnet.com.br/duvidas/pix not in sources; judge must_mention: sim, é preciso uma chave Pix vinculada à conta de recebimento |
| pt-payment-link | pt | knowledge:rag | source https://site.getnet.com.br/duvidas/link-de-pagamento not in sources; judge must_mention: também por redes sociais, e-mail e SMS |
| pt-machines | pt | knowledge:rag | source https://site.getnet.com.br/todas-as-maquininhas not in sources; judge must_mention: Get Smart é Android com estoque e caixa integrados e aceita vale e aplicativos |
| memory-smart-price | en | knowledge:rag | quality: unformatted_amount |
| memory-other-terminal-pt | pt | support>knowledge:rag | route 'support>knowledge:rag' != 'support'; judge must_mention: o outro terminal, Get Smart do Balcão, está online; judge must_not: repete apenas a resposta sobre o Caixa 1 |
| hitl-approve-pt | pt | escalation | HTTPStatusError: Client error '422 Unprocessable Entity' for url 'http://localhost:8000/operator/tickets/t_370ea37040/resolve' For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/422 |
| rag-pix-fee-en | en | knowledge:rag | judge must_mention: the customer pays by scanning a QR code on the machine |
| support-sales-yesterday-en | en | support | judge must_mention: yesterday's sales: R$ 1,250.00 and R$ 489.90, total R$ 1,739.90 |

## Adjudication (judge and code disagree)

- official-01-machines: quality ['unformatted_amount'], judge clarity 5
- official-10-payment-link: code fails (source https://site.getnet.com.br/duvidas/link-de-pagamento not in sources), judge correctness 5
- pt-payment-link: code fails (source https://site.getnet.com.br/duvidas/link-de-pagamento not in sources), judge correctness 4
- pt-machines: code fails (source https://site.getnet.com.br/todas-as-maquininhas not in sources), judge correctness 4
- memory-smart-price: quality ['unformatted_amount'], judge clarity 4
