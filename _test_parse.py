"""Test parse_filename() with user's edge case examples."""
import re, sys, os
sys.path.insert(0, r'd:\FLOW\Crawl')

from haiquan_scraper import parse_filename

tests = [
    # Standard patterns (existing)
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/9/7/2022-T08T-5N(VN-SB).pdf",
     "SB_2022T8_5N.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/4/29/2021-T07K1-1N(VN-CT).pdf",
     "CT_2021T7K1_1N.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/4/29/6542021-T08K2-1N(VN-CT).pdf",
     "CT_2021T8K2_1N.pdf"),

    # User's new edge cases
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2010/3/1/2010-T03K02-13B(VN-CT).pdf",
     "CT_2010T3K2_13B.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2017/5/1/2015-T5T-4(VN-CT)-2017.pdf",
     "CT_2015T5_4.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2017/4/26/2016-T10T-2N(VN-CT) 26-4-17.pdf",
     "CT_2016T10_2N.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2020/8/1/2020-T08T-5N(VN-CT)-final.pdf",
     "CT_2020T8_5N.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2015/9/1/2015-T09T-2X (VN-SB).pdf",
     "SB_2015T9_2X.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2020/11/1/2020-T11-4(VN-SB).pdf",
     "SB_2020T11_4.pdf"),

    # Quarter patterns (new Arabic numeral)
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2020/12/1/Bieu HTX_2020- Q4.pdf",
     "CT_2020Q4_HTX.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2020/6/1/579HTX-Q2-2020.pdf",
     "CT_2020Q2_HTX.pdf"),

    # Existing quarter patterns (still work)
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/6/10/PTVT-NKQ2-final.pdf",
     "CT_2023Q2_PTVT.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/4/29/Bieu HTX_QIV_2021.pdf",
     "CT_2021Q4_HTX.pdf"),
]

passed = 0
failed = 0
for url, expected in tests:
    result = parse_filename(url)
    actual = result['filename'] if result else 'PARSE_FAILED'
    fn = url.split('/')[-1]
    if actual == expected:
        print(f"  PASS  {fn} -> {actual}")
        passed += 1
    else:
        print(f"  FAIL  {fn}")
        print(f"        Expected: {expected}")
        print(f"        Got:      {actual}")
        failed += 1

print(f"\nResults: {passed} passed, {failed} failed / {len(tests)} total")
