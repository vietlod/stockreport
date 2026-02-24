"""
Stock Data Registry
===================
Load và cache dữ liệu ticker từ 3 file Excel:
  - stock_exchange.xlsx: ticker ↔ sàn giao dịch
  - stock_industry.xlsx: ticker ↔ ngành ICB
  - stock_index.xlsx:    ticker ↔ chỉ số (many-to-many)

Usage:
    from stock_data import registry
    registry.get_exchange("ACB")        # → "HNX"
    registry.get_icb_code("ACB")        # → "8770"
    registry.tickers_by_exchange("HOSE") # → ["AAA", "ACB", ...]
"""

import logging
from pathlib import Path
from collections import defaultdict

import openpyxl

log = logging.getLogger("stock_data")

DOCS_DIR = Path(__file__).parent / "docs"


class StockRegistry:
    """Singleton registry cho dữ liệu ticker."""

    def __init__(self, docs_dir: Path = DOCS_DIR):
        self.docs_dir = docs_dir

        # ticker → exchange (str)
        self._exchange: dict[str, str] = {}
        # ticker → type (str: "ST", "FU", etc.)
        self._type: dict[str, str] = {}
        # ticker → icb info (dict)
        self._industry: dict[str, dict] = {}
        # ticker → list of index codes
        self._indexes: dict[str, list[str]] = defaultdict(list)

        # Reverse maps
        self._by_exchange: dict[str, list[str]] = defaultdict(list)
        self._by_icb_code: dict[str, list[str]] = defaultdict(list)
        self._by_index: dict[str, list[str]] = defaultdict(list)

        # All unique values
        self._all_exchanges: list[str] = []
        self._all_icb: list[dict] = []
        self._all_indexes: list[str] = []

        self._loaded = False

    def load(self):
        """Load tất cả dữ liệu từ Excel files."""
        if self._loaded:
            return
        self._load_exchange()
        self._load_industry()
        self._load_index()
        self._loaded = True
        log.info(
            f"📊 StockRegistry loaded: "
            f"{len(self._exchange)} tickers, "
            f"{len(self._all_exchanges)} sàn, "
            f"{len(self._all_icb)} ngành ICB, "
            f"{len(self._all_indexes)} chỉ số"
        )

    def _load_exchange(self):
        """Load stock_exchange.xlsx → ticker ↔ exchange."""
        path = self.docs_dir / "stock_exchange.xlsx"
        if not path.exists():
            log.warning(f"⚠ Không tìm thấy {path}")
            return

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        exchanges_set = set()

        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:  # skip header
                continue
            ticker, exchange, _id, _type = (
                str(row[0] or "").strip().upper(),
                str(row[1] or "").strip().upper(),
                row[2],
                str(row[3] or "").strip().upper(),
            )
            if not ticker or not exchange:
                continue

            self._exchange[ticker] = exchange
            self._type[ticker] = _type
            self._by_exchange[exchange].append(ticker)
            exchanges_set.add(exchange)

        wb.close()
        # Sắp xếp: HOSE, HNX, UPCOM trước, DELISTED cuối
        priority = {"HOSE": 0, "HNX": 1, "UPCOM": 2}
        self._all_exchanges = sorted(
            exchanges_set, key=lambda x: (priority.get(x, 99), x)
        )
        log.info(f"  ✔ Exchange: {len(self._exchange)} tickers, sàn: {self._all_exchanges}")

    def _load_industry(self):
        """Load stock_industry.xlsx → ticker ↔ ICB code/name."""
        path = self.docs_dir / "stock_industry.xlsx"
        if not path.exists():
            log.warning(f"⚠ Không tìm thấy {path}")
            return

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        icb_set = {}  # code → name

        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:  # skip header
                continue
            # columns: ticker, icb_code, icb_name2, en_icb_name2,
            #          icb_name3, en_icb_name3, icb_name4, en_icb_name4,
            #          icb_code1, icb_code2, icb_code3, icb_code4
            ticker = str(row[0] or "").strip().upper()
            icb_code = str(row[1] or "").strip()
            icb_name2 = str(row[2] or "").strip()
            icb_name3 = str(row[4] or "").strip() if len(row) > 4 else ""
            icb_name4 = str(row[6] or "").strip() if len(row) > 6 else ""

            if not ticker or not icb_code:
                continue

            info = {
                "icb_code": icb_code,
                "icb_name2": icb_name2,  # Ngành cấp 2 (chính)
                "icb_name3": icb_name3,  # Ngành cấp 3
                "icb_name4": icb_name4,  # Ngành cấp 4 (chi tiết)
            }
            self._industry[ticker] = info
            self._by_icb_code[icb_code].append(ticker)

            if icb_code not in icb_set:
                icb_set[icb_code] = icb_name2

        wb.close()
        # Sắp xếp theo ICB code
        self._all_icb = sorted(
            [{"code": k, "name": v} for k, v in icb_set.items()],
            key=lambda x: x["code"],
        )
        log.info(f"  ✔ Industry: {len(self._industry)} tickers, {len(self._all_icb)} ngành ICB")

    def _load_index(self):
        """Load stock_index.xlsx → ticker ↔ index codes (many-to-many)."""
        path = self.docs_dir / "stock_index.xlsx"
        if not path.exists():
            log.warning(f"⚠ Không tìm thấy {path}")
            return

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        indexes_set = set()

        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
            ticker = str(row[0] or "").strip().upper()
            index_code = str(row[1] or "").strip()

            if not ticker or not index_code:
                continue

            self._indexes[ticker].append(index_code)
            self._by_index[index_code].append(ticker)
            indexes_set.add(index_code)

        wb.close()
        # Sắp xếp: VN30, VN100, VNMidCap, VNSmallCap, ...
        priority = {"VN30": 0, "VN100": 1, "VNMidCap": 2, "VNSmallCap": 3}
        self._all_indexes = sorted(
            indexes_set, key=lambda x: (priority.get(x, 99), x)
        )
        log.info(f"  ✔ Index: {sum(len(v) for v in self._indexes.values())} mappings, {len(self._all_indexes)} chỉ số")

    # ── Lookup functions ────────────────────────────────────────────

    def get_exchange(self, ticker: str) -> str:
        """Lấy sàn giao dịch của ticker."""
        self.load()
        return self._exchange.get(ticker.upper(), "")

    def get_ticker_type(self, ticker: str) -> str:
        """Lấy loại ticker (ST=cổ phiếu, FU=phái sinh, etc.)."""
        self.load()
        return self._type.get(ticker.upper(), "")

    def get_icb_code(self, ticker: str) -> str:
        """Lấy ICB code (ngành) của ticker."""
        self.load()
        info = self._industry.get(ticker.upper())
        return info["icb_code"] if info else ""

    def get_icb_name(self, ticker: str) -> str:
        """Lấy tên ngành ICB cấp 2 của ticker."""
        self.load()
        info = self._industry.get(ticker.upper())
        return info["icb_name2"] if info else ""

    def get_icb_info(self, ticker: str) -> dict:
        """Lấy toàn bộ thông tin ngành ICB của ticker."""
        self.load()
        return self._industry.get(ticker.upper(), {})

    def get_indexes(self, ticker: str) -> list[str]:
        """Lấy danh sách chỉ số mà ticker thuộc về."""
        self.load()
        return self._indexes.get(ticker.upper(), [])

    # ── Group-by functions ──────────────────────────────────────────

    def tickers_by_exchange(self, exchange: str) -> list[str]:
        """Tất cả tickers của một sàn."""
        self.load()
        return sorted(self._by_exchange.get(exchange.upper(), []))

    def tickers_by_icb_code(self, icb_code: str) -> list[str]:
        """Tất cả tickers của một ngành ICB."""
        self.load()
        return sorted(self._by_icb_code.get(str(icb_code), []))

    def tickers_by_index(self, index_code: str) -> list[str]:
        """Tất cả tickers thuộc một chỉ số."""
        self.load()
        return sorted(self._by_index.get(index_code, []))

    # ── All unique values ───────────────────────────────────────────

    def all_exchanges(self) -> list[str]:
        """Danh sách tất cả sàn."""
        self.load()
        return self._all_exchanges

    def all_icb_codes(self) -> list[dict]:
        """Danh sách tất cả ngành ICB [{code, name}]."""
        self.load()
        return self._all_icb

    def all_indexes(self) -> list[str]:
        """Danh sách tất cả chỉ số."""
        self.load()
        return self._all_indexes

    # ── Stats ───────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Thống kê tổng quan."""
        self.load()
        return {
            "total_tickers": len(set(
                list(self._exchange.keys()) +
                list(self._industry.keys())
            )),
            "exchanges": {
                ex: len(self._by_exchange[ex])
                for ex in self._all_exchanges
            },
            "icb_groups": len(self._all_icb),
            "indexes": {
                idx: len(self._by_index[idx])
                for idx in self._all_indexes
            },
        }

    def to_json(self) -> dict:
        """Export toàn bộ data cho API/frontend."""
        self.load()
        return {
            "exchanges": [
                {"code": ex, "count": len(self._by_exchange[ex])}
                for ex in self._all_exchanges
            ],
            "industries": [
                {**icb, "count": len(self._by_icb_code[icb["code"]])}
                for icb in self._all_icb
            ],
            "indexes": [
                {"code": idx, "count": len(self._by_index[idx])}
                for idx in self._all_indexes
            ],
        }


# ── Singleton instance ──────────────────────────────────────────────────────

registry = StockRegistry()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    registry.load()

    stats = registry.stats()
    print(f"\n{'='*50}")
    print(f"Total tickers: {stats['total_tickers']}")
    print(f"\nExchanges:")
    for ex, cnt in stats["exchanges"].items():
        print(f"  {ex:10s}: {cnt:4d} tickers")
    print(f"\nICB groups: {stats['icb_groups']}")
    print(f"\nIndexes:")
    for idx, cnt in stats["indexes"].items():
        print(f"  {idx:15s}: {cnt:4d} tickers")

    # Test lookups
    print(f"\n{'='*50}")
    for t in ["ACB", "VNM", "FPT", "HPG"]:
        print(
            f"  {t}: exchange={registry.get_exchange(t)} "
            f"icb={registry.get_icb_code(t)} ({registry.get_icb_name(t)}) "
            f"indexes={registry.get_indexes(t)}"
        )
