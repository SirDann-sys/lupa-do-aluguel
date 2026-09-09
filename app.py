import streamlit as st

from analyzer import analisar
from splitter import split_clausulas

st.set_page_config(page_title="TrapDoor", page_icon="🚪")
st.title("TrapDoor — Análise de Contrato de Aluguel")
st.caption(
    "Fase 1: valida se o LLM identifica cláusulas abusivas contra as "
    "7 regras da Lei do Inquilinato. Sem RAG, sem deploy — só a lógica."
)

texto = st.text_area(
    "Cole o texto do contrato de aluguel:",
    height=300,
    placeholder="CLÁUSULA PRIMEIRA – DO OBJETO\n...",
)

if st.button("Analisar", type="primary", disabled=not texto.strip()):
    clausulas = split_clausulas(texto)

    if not clausulas:
        st.warning(
            "Nenhuma cláusula reconhecida no texto. Verifique se o "
            "contrato tem separação por parágrafos ou numeração."
        )
    else:
        with st.spinner(f"Analisando {len(clausulas)} cláusula(s)..."):
            try:
                resultado = analisar(clausulas)
            except RuntimeError as e:
                st.error(str(e))
                resultado = []

        if resultado:
            abusivas = [r for r in resultado if r["classificacao"] == "abusiva"]
            sem_alerta = [r for r in resultado if r["classificacao"] != "abusiva"]

            st.subheader(
                f"{len(resultado)} cláusula(s) analisada(s) — "
                f"{len(abusivas)} abusiva(s)"
            )

            for item in abusivas:
                violacoes_texto = "\n\n".join(
                    f"**Regra {v['regra']} — {v['artigo']}**\n\n{v['explicacao']}"
                    for v in item["violacoes"]
                )
                st.error(f"> {item['clausula']}\n\n{violacoes_texto}")

            if sem_alerta:
                with st.expander(f"{len(sem_alerta)} cláusula(s) sem alerta"):
                    for item in sem_alerta:
                        st.markdown(f"- {item['clausula']}")
