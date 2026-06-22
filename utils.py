"""Funções utilitárias: limpeza de telefone (com a CORREÇÃO do bug do zero) e fuzzy match de nomes."""
import math
import re


def limpar_telefone(v):
    """Normaliza um número para o formato do wa.me (só dígitos, com DDI 55).

    CORRIGE o bug do app antigo: a planilha guarda o número como float
    (ex.: 5581988351851.0) e a limpeza antiga deixava o '0' do '.0' grudado
    no fim, gerando um número inválido. Aqui removemos a parte decimal antes.
    """
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    # remove a parte decimal do float ("5581988351851.0" -> "5581988351851")
    if "." in s:
        s = s.split(".", 1)[0]
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return None
    # adiciona o código do Brasil só quando claramente falta (10 ou 11 dígitos = DDD + número)
    if len(digits) in (10, 11):
        digits = "55" + digits
    return digits


def limpar_email(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    return s


# ── Fuzzy match (igual ao app antigo: Jaccard sobre bigramas de nomes normalizados) ──
_SUFIXOS = re.compile(
    r"\s+(LTDA|S\.?A\.?|EIRELI|ME|EPP|IMPORTACAO|IMPORTAÇÃO|COMERCIO|COMÉRCIO|"
    r"IND\.?|INC\.?|CORP\.?)\.?$"
)


def normalizar(s) -> str:
    s = str(s).upper().strip()
    s = _SUFIXOS.sub("", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def similaridade(a, b) -> int:
    """0-100. Jaccard sobre bigramas dos nomes normalizados."""
    def bigramas(s):
        s = normalizar(s)
        return {s[i:i + 2] for i in range(len(s) - 1)}

    ba, bb = bigramas(a), bigramas(b)
    if not ba or not bb:
        return 0
    return int(100 * len(ba & bb) / len(ba | bb))
