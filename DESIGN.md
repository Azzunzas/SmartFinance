# SmartFinance — Direção de Design

## Propósito

SmartFinance é um painel pessoal de saúde financeira. Ele não é um extrato bancário puro: deve permitir entender saldo, dívida, compromissos, orçamento e recorrências em poucos segundos.

## Princípios visuais

- Tema escuro único, sóbrio e de alta legibilidade.
- Informação financeira primeiro; decoração só quando ajuda a leitura.
- Poucas cores e sempre com significado:
  - verde: entrada, saldo saudável, dentro do orçamento;
  - vermelho: saída, dívida, fatura ou orçamento excedido;
  - amarelo: atenção;
  - azul: informação, navegação e ação neutra;
  - cinza: metadados e estados secundários.
- Superfícies escuras, bordas discretas, cantos moderadamente arredondados e espaçamento consistente.
- Valores monetários usam BRL e devem ser visualmente proeminentes.
- Não usar dados fictícios para preencher telas. Quando não houver API, usar um estado vazio explícito e útil.

## Navegação

Rotas principais:

- Visão Geral
- Transações
- Orçamento
- Recorrências
- Cartões
- Contas
- Metas

Em desktop, a navegação é uma sidebar fixa e recolhível; no modo recolhido, manter ícones e `title`/rótulo acessível. Em mobile, a navegação vira uma faixa horizontal rolável.

## Estrutura de informação

### Visão Geral

Ordem recomendada:

1. Título e contexto de período.
2. Patrimônio líquido, saldo disponível, cartões e investimentos.
3. Saúde financeira em estado preparado enquanto não houver cálculo real.
4. Receitas × despesas dos últimos seis meses e gastos por categoria com seletor de mês.
5. Evolução do patrimônio líquido nos últimos 90 dias.
6. Compromissos futuros em gráfico de barras, com seletor de 6/12 meses e total do período.
7. Alertas de conexão.
8. Últimas transações em estado preparado até existir endpoint específico para a Overview.

### Transações

É a área operacional: deve mostrar transações brutas, inclusive transferências internas e pagamentos de fatura, pois é onde classificações incorretas são auditadas.

Campos disponíveis:

- data e competência;
- descrição e estabelecimento;
- entrada/saída e valor;
- conta ou cartão;
- categoria, quando houver;
- status lançado/pendente;
- parcelas;
- PIX, TED, DOC ou boleto, quando informado;
- flags de transferência interna, pagamento de fatura e exclusão da análise.

Filtros já suportados pela API:

- busca por descrição;
- mês;
- direção;
- conta/cartão;
- meio de pagamento;
- paginação por cursor opaco.

Regras:

- Ao mudar um filtro, reiniciar o cursor.
- Não apresentar paginação como offset/número de página.
- Não oferecer filtro de categoria até existir um catálogo de categorias.
- O backend ordena por data decrescente; não simular outras ordenações.
- O próximo fluxo funcional é classificação manual individual e em lote. O PATCH deve enviar apenas campos que o usuário alterou para não sobrescrever classificações com `null`/`false` involuntariamente.

### Orçamento

O orçamento usa o agregado planejado × realizado por mês.

Cada item deve mostrar:

- nome e tipo;
- valor esperado;
- valor realizado;
- barra de progresso;
- estado pela tolerância.

Semântica atual:

- despesa acima de `esperado + tolerância` fica negativa;
- receita abaixo da tolerância fica em atenção;
- itens sem match devem continuar aparecendo como “Sem lançamento no período”.

O seletor de mês deve consultar `planned-vs-actual?period=YYYY-MM`; a vigência é aplicada pelo backend.

### Recorrências

Exibir em cards separados para receitas e despesas recorrentes.

Cada card contém descrição, valor médio, intervalo médio, número de ocorrências, índice de regularidade, última ocorrência e estado de promoção para orçamento. O topo mostra receitas recorrentes, despesas recorrentes e saldo recorrente esperado.

### Contas

Usar `GET /api/accounts?type=BANK`.

Cada card pode mostrar nome, subtipo, máscara, saldo, inclusão na análise e última atualização. Evitar repetir nomes técnicos de instituições.

### Cartões

Usar `GET /api/accounts?type=CREDIT`.

Cada card pode mostrar nome, bandeira, máscara, fatura, limite, disponível, utilização, vencimento, fechamento, pagamento mínimo e atualização. Fatura usa vermelho; utilização alta usa amarelo.

### Metas

Ainda não existe modelo, endpoint nem persistência. A tela deve ter somente estrutura visual vazia: progresso geral, total acumulado, objetivo total e área “Minhas metas”, sem valores ou barras inventadas. O botão de criação deve permanecer indisponível até o domínio existir.

## Componentes reutilizáveis

- sidebar e item de navegação;
- cards de resumo;
- badges semânticos;
- barras de progresso;
- gráficos ECharts apenas quando houver série real;
- filtros compactos;
- modal de criação/edição;
- lista de transações responsiva;
- paginação por cursor;
- estados de carregamento, erro e vazio.

## Dados que ainda não suportam visualização real

Não criar gráficos ou números simulados para:

- nota de saúde financeira;
- metas financeiras;
- parcelas futuras por cartão;

Quando esses dados não existirem, usar o componente de estado vazio do design system e explicar em uma frase curta qual capacidade será habilitada posteriormente.

## Responsividade e acessibilidade

- Priorizar desktop para leitura de tabelas e dashboards, sem perder funcionalidade em mobile.
- Em telas pequenas, empilhar cards e reduzir colunas secundárias da lista de transações.
- Usar botões com rótulos acessíveis, foco visível e contraste suficiente.
- Modais devem poder ser fechados por `Esc`, devolver o foco ao gatilho e impedir interação com o conteúdo ao fundo.
- Informações críticas não podem depender só de cor: usar texto, badge ou ícone complementar.
