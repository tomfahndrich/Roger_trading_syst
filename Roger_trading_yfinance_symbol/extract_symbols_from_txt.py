import re
import pandas as pd
import argparse


def extract_symbols_from_txt(input_file, output_excel):

    with open(input_file, "r", encoding="utf-8") as f:
        text = f.read()

    # Regex: capture everything after ":" until next ","
    matches = re.findall(r":([^,]+)", text)

    # Clean symbols
    symbols = []
    for m in matches:
        s = m.strip()

        # Skip category headers like ###BANKS STOCKS
        if s.startswith("###"):
            continue

        symbols.append(s)

    # Remove duplicates while preserving order
    symbols = list(dict.fromkeys(symbols))

    # Create dataframe
    df = pd.DataFrame(symbols, columns=["Symbol"])

    # Export to Excel
    df.to_excel(output_excel, index=False)

    print(f"✅ Done — {len(symbols)} symbols extracted")
    print(f"📁 Output file: {output_excel}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("input_txt", help="Input .txt file")
    parser.add_argument("-o", "--output", default="symbols_extracted.xlsx", help="Output Excel file")

    args = parser.parse_args()

    extract_symbols_from_txt(args.input_txt, args.output)