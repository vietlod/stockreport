"""Test parse_filename() với tất cả examples từ user."""
from haiquan_scraper import parse_filename

tests = [
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/9/7/2022-T08T-5N(VN-SB).pdf",
     "SB_2022T8_5N.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/4/29/2021-T07K1-1N(VN-CT).pdf",
     "CT_2021T7K1_1N.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/4/29/6542021-T08K2-1N(VN-CT).pdf",
     "CT_2021T8K2_1N.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/4/29/2021-T07T-2X(VN-CT).pdf",
     "CT_2021T7_2X.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/6/10/PTVT-NKQ2-final.pdf",
     "CT_2021Q2_PTVT.pdf"),
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/4/29/2452021-T08K2-1X(VN-CT).pdf",
     "CT_2021T8K2_1X.pdf"),
    # DC test
    ("https://files.customs.gov.vn/CustomsCMS/TONG_CUC/2022/9/7/2022-T08T-5N(VN-DC).pdf",
     "DC_2022T8_5N.pdf"),
]

passed = 0
failed = 0

for url, expected in tests:
    result = parse_filename(url)
    actual = result["filename"] if result else "NONE"
    if actual == expected:
        passed += 1
        print(f"  OK  {url.split('/')[-1]:50s} -> {actual}")
    else:
        failed += 1
        print(f"  FAIL {url.split('/')[-1]:50s}")
        print(f"       Expected: {expected}")
        print(f"       Got:      {actual}")
        if result:
            print(f"       Meta: {result}")

print(f"\nResults: {passed}/{passed + failed} passed")
if failed:
    print("SOME TESTS FAILED!")
    exit(1)
else:
    print("ALL TESTS PASSED!")
