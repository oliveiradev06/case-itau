# Uso de IA no desenvolvimento

**Ferramenta:** Claude Code (Anthropic), usado como par de programação durante todo o case — análise exploratória dos dados, geração do notebook e dos módulos, e redação inicial da documentação. Todas as decisões de tratamento de dados e interpretação do enunciado foram revisadas e validadas por mim antes de entrar no repositório, e os números das regras foram conferidos com execuções em pandas independentes do texto gerado.

**Onde a IA ajudou mais:** varredura inicial de qualidade dos dados (duplicatas, datas nulas, moedas misturadas) e a percepção de que a limpeza muda o resultado da Regra 1 (falso positivo do CLI-A-3 com a duplicata mantida).

**Onde a IA errou e eu percebi:** na primeira análise do `dados_nivel_2.json`, o assistente afirmou haver **2** registros duplicados (OP-00269 e OP-00160). Ao rodar o diagnóstico completo em pandas, encontrei **5** duplicatas exatas (OP-00040, OP-00160, OP-00214, OP-00269, OP-00272) — a leitura por amostragem do modelo subestimou o problema. Ficou a lição que guiou o resto do case: conclusão de LLM sobre dados se confere com código determinístico, que é exatamente o princípio que o desafio pede (pandas calcula, LLM interpreta).
