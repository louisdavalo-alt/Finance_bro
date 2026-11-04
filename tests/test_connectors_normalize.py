"""Tests unitaires de `normalize()` pour chaque connecteur : aucune dépendance réseau,
uniquement des réponses figées représentatives du format documenté de chaque source.
"""
import asyncio
from pathlib import Path

import pandas as pd
import pytest

from app.connectors.base import IndicatorSpec
from app.connectors.boj import BojConnector, BojFileNotFound, BojFormatError
from app.connectors.ecb import EcbConnector
from app.connectors.estat import EstatConnector
from app.connectors.fred import FredConnector
from app.connectors.imf import ImfConnector, ImfFormatError
from app.connectors.manual import ManualCsvConnector
from app.connectors.nbs_china import NbsChinaConnector
from app.connectors.worldbank import WorldBankConnector

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    raw = (FIXTURES / name).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "shift_jis"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise AssertionError(f"impossible de décoder la fixture {name}")


def _spec(code="X", connector="fred", frequency="M", **params):
    return IndicatorSpec(code, "USA", connector, frequency, "u", params, publication_lag_days=10)


def _connector(cls):
    return cls(client=None, store=None, cache_ttl_s={})  # normalize() n'utilise ni client ni store


def test_fred_normalize_skips_dot_values():
    raw = {"observations": [
        {"date": "2024-01-01", "value": "5.25"},
        {"date": "2024-02-01", "value": "."},  # valeur manquante FRED
        {"date": "2024-03-01", "value": "5.50"},
    ]}
    df = _connector(FredConnector).normalize(raw, _spec())
    assert df["value"].tolist() == [5.25, 5.50]
    assert (df["release_date"] - df["timestamp"]).dt.days.tolist() == [10, 10]


def test_ecb_normalize_reads_csvdata():
    raw = "KEY;TIME_PERIOD;OBS_VALUE\nD.U2.EUR.4F.KR.DFR.LEV;2024-01-02;4.00\nD.U2.EUR.4F.KR.DFR.LEV;2024-01-03;4.00\n".replace(";", ",")
    df = _connector(EcbConnector).normalize(raw, _spec(connector="ecb", frequency="D"))
    assert df["value"].tolist() == [4.00, 4.00]


def test_estat_normalize_parses_monthly_japanese_labels():
    raw = {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": [{"@id": "time", "CLASS": [
                    {"@code": "T1", "@name": "2024年01月"},
                    {"@code": "T2", "@name": "2024年02月"},
                ]}]},
                "DATA_INF": {"VALUE": [
                    {"@time": "T1", "$": "105.2"},
                    {"@time": "T2", "$": "105.5"},
                    {"@time": "T3", "$": "-"},  # code temporel inconnu -> ignoré
                ]},
            }
        }
    }
    df = _connector(EstatConnector).normalize(raw, _spec(connector="estat"))
    assert df["value"].tolist() == [105.2, 105.5]
    assert df["timestamp"].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]


def test_boj_normalize_reads_real_fm01_export():
    """Fixture réelle : export CSV anglais tel que téléchargé depuis stat-search.boj.or.jp."""
    raw = _fixture("fm01_d_1.csv")
    spec = IndicatorSpec("JP_POLICY_RATE", "JPN", "boj", "D", "%", {"filename": "fm01_d_1.csv", "code": "FM01'STRDCLUCON"})
    df = _connector(BojConnector).normalize(raw, spec)
    assert df.iloc[0]["value"] == pytest.approx(0.49)
    assert df.iloc[0]["timestamp"] == pd.Timestamp("1998-01-05")
    assert (df["value"] > -1).all() and (df["value"] < 10).all()  # plage plausible pour un taux


def test_boj_normalize_reads_real_japanese_export():
    """Même fichier, mais l'export japonais (Shift-JIS, libellés en japonais) doit donner le même résultat."""
    raw = _fixture("ir01_d_1.csv")
    spec = IndicatorSpec("JP_DISCOUNT_RATE", "JPN", "boj", "D", "%", {"filename": "ir01_d_1.csv", "code": "IR01'MADR1Z@D"})
    df = _connector(BojConnector).normalize(raw, spec)
    assert df.iloc[0]["value"] == pytest.approx(0.5)
    assert df.iloc[0]["timestamp"] == pd.Timestamp("1998-01-01")


def test_boj_normalize_reads_quarterly_export_with_slash_dates():
    raw = _fixture("ff_q_1_en.csv")
    spec = IndicatorSpec("JP_HH_ASSETS", "JPN", "boj", "Q", "100M JPY", {"filename": "ff_q_1_en.csv", "code": "FF'FOF_FFAS430A900"})
    df = _connector(BojConnector).normalize(raw, spec)
    assert df.iloc[0]["value"] == pytest.approx(12851274)
    assert df.iloc[0]["timestamp"] == pd.Timestamp("1997-12-01")


def test_boj_normalize_raises_on_unknown_code():
    raw = _fixture("fm01_d_1.csv")
    spec = IndicatorSpec("X", "JPN", "boj", "D", "%", {"filename": "fm01_d_1.csv", "code": "CODE_QUI_N_EXISTE_PAS"})
    with pytest.raises(BojFormatError):
        _connector(BojConnector).normalize(raw, spec)


def test_boj_fetch_raw_raises_clear_error_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import load_settings

    settings = load_settings()
    conn = BojConnector(client=type("C", (), {"settings": settings})(), store=None, cache_ttl_s={})
    spec = IndicatorSpec("X", "JPN", "boj", "D", "%", {"filename": "absent.csv"})
    with pytest.raises(BojFileNotFound):
        asyncio.run(conn.fetch_raw(spec))



def test_worldbank_normalize_reads_second_element_and_dates_year_end():
    raw = [{"page": 1}, [
        {"date": "2023", "value": 5.2},
        {"date": "2022", "value": None},  # à ignorer
        {"date": "2021", "value": 8.0},
    ]]
    df = _connector(WorldBankConnector).normalize(raw, _spec(connector="worldbank", frequency="A"))
    assert df["value"].tolist() == [8.0, 5.2]
    assert df["timestamp"].tolist() == [pd.Timestamp("2021-12-31"), pd.Timestamp("2023-12-31")]
    assert (df["frequency"] == "A").all()


def test_nbs_china_normalize_reads_datanodes():
    raw = {"returndata": {"datanodes": [
        {"data": {"data": 5.2}, "wds": [{"wdcode": "sj", "valuecode": "202401"}]},
        {"data": {"data": None}, "wds": [{"wdcode": "sj", "valuecode": "202402"}]},  # ignoré
    ]}}
    df = _connector(NbsChinaConnector).normalize(raw, _spec(connector="nbs_china"))
    assert df["value"].tolist() == [5.2]


def test_manual_csv_normalize_uses_reference_date_as_release_date():
    raw = "date,value\n2024-01-01,6.50\n2024-02-01,6.25\n"
    df = _connector(ManualCsvConnector).normalize(raw, _spec(connector="manual", frequency="D"))
    assert df["value"].tolist() == [6.50, 6.25]
    # Contrairement aux autres sources, pas de délai estimé : release_date == timestamp.
    assert (df["release_date"] == df["timestamp"]).all()


def _imf_spec(code="FR_CPI", key="FRA.CPI.*.IX.M"):
    return IndicatorSpec(code, "FRA", "imf", "M", "indice", {"agency_id": "IMF.STA", "resource_id": "CPI", "version": "+", "key": key}, publication_lag_days=15)


def test_imf_normalize_reads_official_documented_example():
    """Fixture reprise telle quelle de l'exemple officiel de la spec OpenAPI du FMI
    (idata-sdmx-api-3-0.json, réponse 200 du endpoint /data)."""
    raw = {
        "data": {
            "dataSets": [
                {
                    "action": "Information",
                    "series": {"0:0:0:0:0:0": {"attributes": [None], "observations": {"0": ["4.2", 0, None], "1": ["3.8", 0, None]}}},
                    "structure": 0,
                }
            ],
            "structures": [
                {
                    "dimensions": {
                        "observation": [{"id": "TIME_PERIOD", "keyPosition": 6, "values": [{"value": "2023"}, {"value": "2024"}]}],
                        "series": [{"id": "REF_AREA", "keyPosition": 0, "values": [{"id": "FRA"}]}],
                    },
                    "dataSets": [0],
                }
            ],
        },
        "meta": {},
    }
    df = _connector(ImfConnector).normalize(raw, _imf_spec())
    assert df["value"].tolist() == [4.2, 3.8]
    assert df["timestamp"].tolist() == [pd.Timestamp("2023-01-01"), pd.Timestamp("2024-01-01")]


def test_imf_normalize_fixes_sdmx_monthly_period_notation():
    """Bug réel rencontré en production (25/09/2026) : le FMI renvoie des périodes mensuelles
    au format SDMX "AAAA-Mxx" (ex. "1955-M01"), que `pandas.to_datetime` seul interprète mal
    (le "01" de "M01" devient des secondes : 1955-01-01 00:00:01 au lieu de 1955-01-01)."""
    raw = {
        "data": {
            "dataSets": [{"series": {"0": {"observations": {"0": ["6.14", 0, None], "1": ["6.13", 0, None], "11": ["6.18", 0, None]}}}, "structure": 0}],
            "structures": [{"dimensions": {"observation": [{"values": [{"value": "1955-M01"}, {"value": "1955-M02"}] + [{"value": f"1955-M{i:02d}"} for i in range(3, 12)] + [{"value": "1955-M12"}]}], "series": []}}],
        }
    }
    df = _connector(ImfConnector).normalize(raw, _imf_spec())
    assert df["timestamp"].tolist() == [pd.Timestamp("1955-01-01"), pd.Timestamp("1955-02-01"), pd.Timestamp("1955-12-01")]
    # Aucune heure/minute/seconde parasite : les trois dates sont à minuit pile.
    assert all(t.time() == pd.Timestamp("2000-01-01").time() for t in df["timestamp"])


def test_imf_normalize_skips_null_observations():
    raw = {
        "data": {
            "dataSets": [{"series": {"0": {"observations": {"0": ["4.2", 0, None], "1": [None, 0, None]}}}, "structure": 0}],
            "structures": [{"dimensions": {"observation": [{"values": [{"value": "2023"}, {"value": "2024"}]}], "series": []}}],
        }
    }
    df = _connector(ImfConnector).normalize(raw, _imf_spec())
    assert df["value"].tolist() == [4.2]


def test_imf_normalize_raises_on_missing_structures():
    with pytest.raises(ImfFormatError):
        _connector(ImfConnector).normalize({"data": {"dataSets": [{}], "structures": []}}, _imf_spec())


def test_yfinance_normalize_builds_frame_from_prefetched_series():
    """`fetch_raw` est asynchrone et appelle yfinance dans un thread (voir yfin.py) ; on teste
    ici `normalize()` seul, avec une sortie déjà au format que `fetch_raw` produirait."""
    from app.connectors.yfin import YFinanceConnector

    raw = {"dates": ["2024-01-02", "2024-01-03"], "values": [16700.5, 16650.2]}
    spec = IndicatorSpec("DE_DAX", "DEU", "yfinance", "D", "points d'indice", {"symbol": "^GDAXI"})
    df = _connector(YFinanceConnector).normalize(raw, spec)
    assert df["value"].tolist() == [16700.5, 16650.2]
    assert df["timestamp"].tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]


def test_yfinance_normalize_handles_empty_history():
    from app.connectors.yfin import YFinanceConnector

    spec = IndicatorSpec("DE_DAX", "DEU", "yfinance", "D", "points d'indice", {"symbol": "^GDAXI"})
    df = _connector(YFinanceConnector).normalize({"dates": [], "values": []}, spec)
    assert df.empty


def test_boj_normalize_reads_real_balance_of_payments_export():
    """Fixture réelle : remplacement de JP_TRADE_BALANCE après échec du statsDataId e-Stat deviné."""
    raw = _fixture("bp01_m_1_en.csv")
    spec = IndicatorSpec("JP_TRADE_BALANCE", "JPN", "boj", "M", "100M JPY", {"filename": "bp01_m_1_en.csv", "code": "BP01'BPBP6JYNCB"})
    df = _connector(BojConnector).normalize(raw, spec)
    assert df.iloc[0]["value"] == pytest.approx(341.51732161)
    assert df.iloc[0]["timestamp"] == pd.Timestamp("1996-01-01")


def test_boj_normalize_selects_correct_column_among_multiple_series():
    """Le même fichier contient deux séries (compte courant / compte financier) : vérifie
    qu'on récupère bien la bonne colonne selon le code demandé, pas toujours la première."""
    raw = _fixture("bp01_m_1_en.csv")
    spec = IndicatorSpec("X", "JPN", "boj", "M", "100M JPY", {"filename": "bp01_m_1_en.csv", "code": "BP01'BPBP6JYNFB"})
    df = _connector(BojConnector).normalize(raw, spec)
    assert df.iloc[0]["value"] == pytest.approx(-3784.33878933)


def test_tmi_tokyo_normalize_reads_real_export():
    from app.connectors.tmi_tokyo import TmiTokyoConnector

    raw = _fixture("tmi2025c.csv")
    spec = IndicatorSpec("JP_CPI_TOKYO", "JPN", "tmi_tokyo", "M", "indice", {"filename": "tmi2025c.csv", "code": "0901"})
    df = _connector(TmiTokyoConnector).normalize(raw, spec)
    assert df.iloc[0]["value"] == pytest.approx(86.9)
    assert df.iloc[0]["timestamp"] == pd.Timestamp("2010-01-01")


def test_tmi_tokyo_normalize_selects_correct_category_column():
    from app.connectors.tmi_tokyo import TmiTokyoConnector

    raw = _fixture("tmi2025c.csv")
    spec = IndicatorSpec("X", "JPN", "tmi_tokyo", "M", "indice", {"filename": "tmi2025c.csv", "code": "0924"})
    df = _connector(TmiTokyoConnector).normalize(raw, spec)
    assert df.iloc[0]["value"] == pytest.approx(94.2)


def test_tmi_tokyo_normalize_raises_on_unknown_code():
    from app.connectors.tmi_tokyo import TmiTokyoConnector, TmiTokyoFormatError

    raw = _fixture("tmi2025c.csv")
    spec = IndicatorSpec("X", "JPN", "tmi_tokyo", "M", "indice", {"filename": "tmi2025c.csv", "code": "9999"})
    with pytest.raises(TmiTokyoFormatError):
        _connector(TmiTokyoConnector).normalize(raw, spec)
