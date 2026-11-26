# Retrieval report

k = 5; relevance by normalized URL; context recall = expected fact found in any top-k chunk.

| Mode | Lang | N | hit | recall | mrr | ndcg | context_precision | context_recall |
|---|---|---|---|---|---|---|---|---|
| hybrid | all | 16 | 0.812 | 0.708 | 0.594 | 0.582 | 0.400 | 0.875 |
| hybrid | en | 7 | 0.714 | 0.643 | 0.607 | 0.580 | 0.343 | 0.857 |
| hybrid | pt | 9 | 0.889 | 0.759 | 0.583 | 0.584 | 0.444 | 0.889 |
| vector | all | 16 | 0.812 | 0.604 | 0.400 | 0.404 | 0.388 | 0.875 |
| vector | en | 7 | 1.000 | 0.762 | 0.355 | 0.434 | 0.400 | 0.857 |
| vector | pt | 9 | 0.667 | 0.481 | 0.435 | 0.381 | 0.378 | 0.889 |

## Per query

| Query | Mode | Hit | MRR | Fact | Top URLs |
|---|---|---|---|---|---|
| r-crediario-en | hybrid | 1 | 1.00 | 1 | https://site.getnet.com.br/duvidas/crediario, https://site.getnet.com.br/crediario |
| r-crediario-en | vector | 1 | 0.50 | 1 | https://site.getnet.com.br/duvidas, https://site.getnet.com.br/crediario |
| r-crediario-pt | hybrid | 1 | 1.00 | 1 | https://site.getnet.com.br/crediario, https://site.getnet.com.br/duvidas/crediario, https://site.getnet.com.br/duvidas/parcelado |
| r-crediario-pt | vector | 1 | 1.00 | 1 | https://site.getnet.com.br/crediario, https://site.getnet.com.br/duvidas |
| r-machines-en | hybrid | 1 | 1.00 | 1 | https://site.getnet.com.br/todas-as-maquininhas, https://site.getnet.com.br/get-tap, https://site.getnet.com.br/duvidas/get-smart, https://www.getnet.net/en/our-solutions/in-person-payments |
| r-machines-en | vector | 1 | 0.20 | 1 | https://site.getnet.com.br, https://site.getnet.com.br/ofertas, https://site.getnet.com.br/get-tap, https://site.getnet.com.br/todas-as-maquininhas |
| r-machines-pt | hybrid | 1 | 0.50 | 1 | https://site.getnet.com.br/get-tap, https://site.getnet.com.br/todas-as-maquininhas, https://site.getnet.com.br/ofertas, https://site.getnet.com.br |
| r-machines-pt | vector | 0 | 0.00 | 0 | https://site.getnet.com.br/getstore, https://site.getnet.com.br/duvidas/get-smart |
| r-classica-price-pt | hybrid | 1 | 1.00 | 1 | https://site.getnet.com.br/todas-as-maquininhas, https://site.getnet.com.br/get-tap, https://site.getnet.com.br, https://site.getnet.com.br/ofertas |
| r-classica-price-pt | vector | 1 | 0.33 | 1 | https://site.getnet.com.br, https://site.getnet.com.br/get-tap, https://site.getnet.com.br/todas-as-maquininhas, https://site.getnet.com.br/getcheckout, https://site.getnet.com.br/ofertas |
| r-pix-en | hybrid | 1 | 1.00 | 1 | https://site.getnet.com.br/duvidas/pix, https://site.getnet.com.br/duvidas/pix-mais-respostas, https://www.getnet.net/en/your-business/large-enterprises, https://site.getnet.com.br/duvidas, https://site.getnet.com.br/pix |
| r-pix-en | vector | 1 | 0.25 | 0 | https://www.getnet.net/en/your-business/large-enterprises, https://site.getnet.com.br/blog, https://site.getnet.com.br/getcheckout, https://site.getnet.com.br/pix, https://site.getnet.com.br/crediario |
| r-pix-pt | hybrid | 1 | 0.50 | 1 | https://site.getnet.com.br/duvidas/get-conta, https://site.getnet.com.br/duvidas/pix-mais-respostas, https://site.getnet.com.br/duvidas |
| r-pix-pt | vector | 1 | 0.25 | 1 | https://site.getnet.com.br/duvidas, https://site.getnet.com.br/duvidas/pix-mais-respostas |
| r-offline-en | hybrid | 0 | 0.00 | 0 | https://site.getnet.com.br/duvidas/bandeiras, https://site.getnet.com.br/duvidas/get-tap, https://site.getnet.com.br/duvidas, https://site.getnet.com.br/duvidas/aluguel-zero, https://site.getnet.com.br/duvidas/antecipacao-de-vendas |
| r-offline-en | vector | 1 | 0.50 | 1 | https://site.getnet.com.br/duvidas, https://site.getnet.com.br/duvidas/algar, https://www.getnet.net/en/your-business/industries/restaurants, https://site.getnet.com.br/ofertas |
| r-offline-pt | hybrid | 1 | 0.25 | 0 | https://site.getnet.com.br/duvidas/bandeiras, https://site.getnet.com.br/duvidas/antecipacao-de-vendas, https://site.getnet.com.br/imprensa, https://site.getnet.com.br/duvidas/algar, https://site.getnet.com.br |
| r-offline-pt | vector | 0 | 0.00 | 1 | https://site.getnet.com.br/ofertas, https://site.getnet.com.br/get-ajuda, https://site.getnet.com.br, https://site.getnet.com.br/duvidas, https://site.getnet.com.br/todas-as-maquininhas |
| r-advance-en | hybrid | 0 | 0.00 | 1 | https://site.getnet.com.br/duvidas, https://site.getnet.com.br/crediario, https://site.getnet.com.br/duvidas/app-getnet |
| r-advance-en | vector | 1 | 0.33 | 1 | https://site.getnet.com.br/duvidas/app-getnet, https://site.getnet.com.br/duvidas, https://site.getnet.com.br/duvidas/antecipacao-de-vendas |
| r-advance-pt | hybrid | 1 | 0.50 | 1 | https://site.getnet.com.br/duvidas, https://site.getnet.com.br/duvidas/antecipacao-de-vendas, https://site.getnet.com.br/crediario |
| r-advance-pt | vector | 1 | 0.33 | 1 | https://site.getnet.com.br/duvidas, https://www.getnet.net/en/our-solutions/value-added-solutions, https://site.getnet.com.br/duvidas/antecipacao-de-vendas |
| r-link-en | hybrid | 1 | 0.25 | 1 | https://site.getnet.com.br, https://site.getnet.com.br/produtos-digitais, https://www.getnet.net/en/our-solutions/online-payments, https://site.getnet.com.br/duvidas/link-de-pagamento, https://site.getnet.com.br/link-de-pagamento |
| r-link-en | vector | 1 | 0.50 | 1 | https://www.getnet.net/en/our-solutions/online-payments, https://site.getnet.com.br/duvidas/link-de-pagamento, https://site.getnet.com.br/link-de-pagamento, https://site.getnet.com.br/getcheckout |
| r-link-pt | hybrid | 1 | 0.50 | 1 | https://site.getnet.com.br/produtos-digitais, https://site.getnet.com.br/link-de-pagamento, https://site.getnet.com.br, https://site.getnet.com.br/duvidas/link-de-pagamento, https://site.getnet.com.br/get-tap |
| r-link-pt | vector | 1 | 1.00 | 1 | https://site.getnet.com.br/link-de-pagamento, https://site.getnet.com.br/duvidas/link-de-pagamento, https://site.getnet.com.br/blog |
| r-voucher-pt | hybrid | 1 | 1.00 | 1 | https://site.getnet.com.br/duvidas/get-smart |
| r-voucher-pt | vector | 1 | 1.00 | 1 | https://site.getnet.com.br/duvidas/get-smart, https://site.getnet.com.br/duvidas |
| r-pix-qr-en | hybrid | 1 | 1.00 | 1 | https://site.getnet.com.br/pix, https://site.getnet.com.br/duvidas/pix-mais-respostas, https://site.getnet.com.br/duvidas, https://site.getnet.com.br, https://site.getnet.com.br/imprensa |
| r-pix-qr-en | vector | 1 | 0.20 | 1 | https://site.getnet.com.br/duvidas/get-smart, https://site.getnet.com.br/duvidas/pix-mais-respostas, https://site.getnet.com.br/duvidas, https://site.getnet.com.br/duvidas/pix |
| r-cancel-pt | hybrid | 0 | 0.00 | 1 | https://site.getnet.com.br/duvidas/get-conta, https://site.getnet.com.br/duvidas, https://site.getnet.com.br/link-de-pagamento |
| r-cancel-pt | vector | 0 | 0.00 | 1 | https://site.getnet.com.br/link-de-pagamento, https://site.getnet.com.br/duvidas/get-conta, https://site.getnet.com.br/get-tap, https://site.getnet.com.br/emprestimo, https://site.getnet.com.br/ofertas |
