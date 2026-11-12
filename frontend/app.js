"use strict";

// Todo conteúdo vindo da API ou do usuário entra no DOM via textContent,
// nunca innerHTML: um contrato colado não consegue injetar HTML na página.

const API = ["localhost", "127.0.0.1"].includes(location.hostname)
  ? "http://127.0.0.1:8000"
  : "https://lupa-do-aluguel-api.onrender.com";

const TEMPO_MAXIMO_MS = 120_000;
const AVISO_ACORDANDO_MS = 4_000;
const NOMES_PROVEDOR = { groq: "Groq", gemini: "Gemini", heuristico: "modo básico" };

const $ = (id) => document.getElementById(id);

function criar(tag, texto, classe) {
  const el = document.createElement(tag);
  if (texto !== undefined) el.textContent = texto;
  if (classe) el.className = classe;
  return el;
}

function porcentagem(valor) {
  return valor === null || valor === undefined ? "—" : `${Math.round(valor * 100)}%`;
}

// ------------------------------------------------------------------ abas

function configurarAbas() {
  const abas = [...document.querySelectorAll('[role="tab"]')];
  const selecionar = (aba) => {
    for (const outra of abas) {
      const ativa = outra === aba;
      outra.setAttribute("aria-selected", String(ativa));
      outra.tabIndex = ativa ? 0 : -1;
      $(outra.getAttribute("aria-controls")).hidden = !ativa;
    }
    aba.focus();
  };
  for (const aba of abas) {
    aba.addEventListener("click", () => selecionar(aba));
    aba.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const passo = e.key === "ArrowRight" ? 1 : -1;
      selecionar(abas[(abas.indexOf(aba) + passo + abas.length) % abas.length]);
    });
  }
}

const abaAtiva = () => document.querySelector('[role="tab"][aria-selected="true"]').id;

// ------------------------------------------------------------------ status

function status(mensagem, tipo = "") {
  const el = $("status");
  el.textContent = mensagem;
  el.className = `status ${tipo}`;
}

// ------------------------------------------------------------------ exemplos

async function carregarExemplo(nome) {
  try {
    const resposta = await fetch(`exemplos/${nome}.txt`);
    if (!resposta.ok) throw new Error(String(resposta.status));
    $("texto").value = await resposta.text();
    $("texto").focus();
    status("");
  } catch {
    status("Não consegui carregar o exemplo.", "erro");
  }
}

// ------------------------------------------------------------------ análise

async function enviar(evento) {
  evento.preventDefault();
  const botao = $("analisar");
  let pedido;

  if (!$("consentimento").checked) {
    $("consentimento").focus();
    return status("Para analisar, marque a caixa de consentimento sobre o envio do texto.", "erro");
  }

  if (abaAtiva() === "aba-texto") {
    const texto = $("texto").value.trim();
    if (!texto) return status("Cole o texto do contrato ou escolha um exemplo.", "erro");
    pedido = { url: "/v1/analises", opcoes: {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto, consentimento: true }) } };
  } else {
    const arquivo = $("arquivo").files[0];
    if (!arquivo) return status("Escolha o arquivo PDF do contrato.", "erro");
    const dados = new FormData();
    dados.append("arquivo", arquivo);
    dados.append("consentimento", "true");
    pedido = { url: "/v1/analises/pdf", opcoes: { method: "POST", body: dados } };
  }

  botao.disabled = true;
  $("resultado").hidden = true;
  status("Analisando o contrato…", "carregando");
  const acordando = setTimeout(() => status(
    "O servidor gratuito estava dormindo e está acordando. Isso pode levar até 1 minuto.",
    "carregando"), AVISO_ACORDANDO_MS);
  const cancelar = new AbortController();
  const limite = setTimeout(() => cancelar.abort(), TEMPO_MAXIMO_MS);

  try {
    const resposta = await fetch(API + pedido.url, { ...pedido.opcoes, signal: cancelar.signal });
    const corpo = await resposta.json().catch(() => ({}));
    if (!resposta.ok) {
      throw new Error(corpo?.erro?.mensagem || `O servidor respondeu com erro ${resposta.status}.`);
    }
    status("");
    mostrarRelatorio(corpo);
  } catch (erro) {
    const mensagem = erro.name === "AbortError"
      ? "A análise demorou demais. Tente de novo em instantes."
      : erro instanceof TypeError
        ? "Não consegui falar com o servidor. Confira sua conexão e tente de novo."
        : erro.message;
    status(mensagem, "erro");
  } finally {
    clearTimeout(acordando);
    clearTimeout(limite);
    botao.disabled = false;
  }
}

function mostrarRelatorio(relatorio) {
  const { achados, clausulas, provedor, modelo, em_cache: emCache } = relatorio;
  const regras = new Set(achados.map((a) => a.regra));

  $("titulo-resultado").textContent = regras.size
    ? `${regras.size} ${regras.size === 1 ? "problema encontrado" : "problemas encontrados"}`
    : "Nenhum problema encontrado nas 7 regras";

  const linhaProvedor = $("provedor");
  if (provedor === "heuristico") {
    linhaProvedor.textContent = "A IA estava indisponível, então esta análise usou o modo básico " +
      "por palavras-chave, que deixa passar armadilhas disfarçadas. Tente de novo mais tarde.";
    linhaProvedor.className = "provedor basico";
  } else {
    const nome = NOMES_PROVEDOR[provedor] || provedor;
    linhaProvedor.textContent = `${clausulas.length} cláusulas lidas por ${nome} (${modelo})` +
      (emCache ? " · resultado reaproveitado de uma análise idêntica recente" : "") + ".";
    linhaProvedor.className = "provedor";
  }
  if (relatorio.dados_mascarados) {
    const n = relatorio.dados_mascarados;
    linhaProvedor.textContent += ` ${n} ${n === 1 ? "dado pessoal foi mascarado"
      : "dados pessoais foram mascarados"} antes do envio.`;
  }

  const lista = $("achados");
  lista.replaceChildren();
  if (!achados.length) {
    const ok = criar("article", undefined, "achado limpo");
    ok.append(
      criar("h3", "Nada fora das 7 regras"),
      criar("p", "Isso não garante que o contrato é justo: a Lupa só confere estas 7 regras."),
    );
    lista.append(ok);
  }
  for (const achado of achados) {
    const item = criar("article", undefined, "achado");
    const nums = achado.clausulas.map((n) => `${n}ª`).join(", ");
    item.append(
      criar("h3", achado.titulo),
      criar("p", `${achado.artigo} · cláusula ${nums}`, "artigo"),
      criar("p", achado.explicacao),
    );
    for (const trecho of achado.trechos) item.append(criar("blockquote", `“${trecho}”`));
    const orientacao = criar("p", undefined, "orientacao");
    orientacao.append(criar("strong", "O que pedir: "), achado.orientacao);
    item.append(orientacao);
    lista.append(item);
  }

  const ol = $("clausulas");
  ol.replaceChildren();
  for (const clausula of clausulas) {
    const li = criar("li");
    if (clausula.regras.length) {
      li.className = "marcada";
      for (const r of clausula.regras) li.append(criar("span", `regra ${r}`, "selo"));
    }
    li.append(clausula.texto);
    ol.append(li);
  }

  const secao = $("resultado");
  secao.hidden = false;
  secao.focus();
}

// ------------------------------------------------------------------ regras e métricas

async function carregarRegras() {
  const lista = $("regras");
  try {
    const regras = await (await fetch(`${API}/v1/regras`)).json();
    lista.replaceChildren(...regras.map((r) => {
      const li = criar("li");
      li.append(criar("strong", r.titulo), " ", criar("small", `(${r.artigo})`));
      return li;
    }));
  } catch {
    lista.replaceChildren(criar("li", "As regras aparecem quando o servidor responder."));
  }
}

async function carregarMetricas() {
  const alvo = $("metricas");
  const linhas = [];
  for (const nome of ["groq", "gemini", "heuristico"]) {
    try {
      const resposta = await fetch(`dados/${nome}.json`);
      if (resposta.ok) linhas.push(await resposta.json());
    } catch { /* arquivo ausente: provedor ainda não avaliado */ }
  }
  if (!linhas.length) {
    alvo.replaceChildren(criar("p", "Ainda não há avaliação publicada."));
    return;
  }

  const tabela = criar("table");
  tabela.append(criar("caption", `Última avaliação: ${linhas[0].gerado_em.slice(0, 10)}`));
  const cabeca = criar("tr");
  for (const t of ["Extrator", "Conjunto", "Contratos exatos", "Precisão", "Recall"]) {
    const th = criar("th", t);
    th.scope = "col";
    cabeca.append(th);
  }
  const thead = criar("thead");
  thead.append(cabeca);
  tabela.append(thead);
  const corpo = criar("tbody");
  for (const dados of linhas) {
    for (const [conjunto, c] of Object.entries(dados.conjuntos)) {
      const tr = criar("tr");
      const nome = dados.provedor === "heuristico" ? "Modo básico (sem IA)"
        : `${NOMES_PROVEDOR[dados.provedor]} · ${dados.modelo}`;
      tr.append(
        criar("td", nome),
        criar("td", conjunto === "teste_cego" ? "teste cego" : "desenvolvimento"),
        criar("td", `${c.contratos_certos} de ${c.contratos}`),
        criar("td", porcentagem(c.precisao)),
        criar("td", porcentagem(c.recall)),
      );
      corpo.append(tr);
    }
  }
  tabela.append(corpo);
  const rolagem = criar("div", undefined, "tabela-rolagem");
  rolagem.append(tabela);
  alvo.replaceChildren(rolagem);
}

// ------------------------------------------------------------------ início

configurarAbas();
$("formulario").addEventListener("submit", enviar);
for (const botao of document.querySelectorAll("[data-exemplo]")) {
  botao.addEventListener("click", () => carregarExemplo(botao.dataset.exemplo));
}
carregarRegras();   // de quebra, já acorda o servidor enquanto a pessoa lê a página
carregarMetricas();
