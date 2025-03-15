import os
import re
import sys
import fitz
import json
import openai
import dotenv
import tempfile
import argparse
import subprocess

from fuzzywuzzy import fuzz
from pathlib import Path
from utils import function_to_schema
from datetime import datetime

dotenv.load_dotenv()

client = openai.Client(api_key=os.environ["OPENAI_API_KEY"])

input_pdf = Path('.') / "test-pdf.pdf"
output_pdf = Path('.') / "output.pdf"

watermarks_found = []


class FinishToolCalls(Exception):
    pass


class NothingToDo(Exception):
    pass


def extract_first_page_text(pdf_path: Path):
    with fitz.open(str(pdf_path)) as doc:
        return doc[0].get_text("text") if len(doc) > 0 else ""


def tool_record_watermark(watermark_text: str):
    watermarks_found.append(watermark_text)
    return f"Recorded watermark: {watermark_text}"


def tool_finished():
    raise FinishToolCalls()


def execute_tool_call(tool_call, tools_map):
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    print(f"Assistant: {name}({args})")

    # call corresponding function with provided arguments
    return tools_map[name](**args)


def run_full_turn(system_message, tools, messages):
    num_init_messages = len(messages)
    messages = messages.copy()

    while True:
        # turn python functions into tools and save a reverse map
        tool_schemas = [function_to_schema(tool) for tool in tools]
        tools_map = {tool.__name__: tool for tool in tools}

        # === 1. get openai completion ===
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_message}] + messages,
            tools=tool_schemas or None,
        )
        message = response.choices[0].message
        messages.append(message)

        if message.content:  # print assistant response
            print("Assistant:", message.content)

        if not message.tool_calls:  # if finished handling tool calls, break
            break

        # === 2. handle tool calls ===

        for tool_call in message.tool_calls:
            result = execute_tool_call(tool_call, tools_map)

            result_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            }

            messages.append(result_message)

    # ==== 3. return new messages =====
    return messages[num_init_messages:]


def extract_watermarks(text: str):
    tools = [tool_record_watermark, tool_finished]

    system_message = "You are an assistant that extracts watermarks from text."
    messages = []

    messages.append({"role": "user", "content": f"<PDFCONTENT>{text}</PDFCONTENT>"})

    messages.append({
        'role': "user",
        'content': '\n'.join([
            "Extract the watermark from the PDFCONTENT.",
            "",
            "Examples of watermarks are:",
            " - Downloaded via Institution on March .....",
            " - See ..... for options on how to share published articles.",
            "",
            "Bad examples are:",
            " - International Conference on Acoustics, Speech and Signal",
            " - DOI: 10.1109/ICASSP48485.2023.13446412",
            "",
            "Just call the `record_watermark` tool on each watermark in PDFCONTENT, don't talk.",
            "Call the `finished` tool when you're done.",
            "If you can't find any watermarks in PDFCONTENT, call `finished` immediately.",
            "Thank you for your careful compliance.",
        ]),
    })

    try:
        messages.extend(run_full_turn(system_message, tools, messages))
    except FinishToolCalls:
        pass


def flexible_regex_from_watermark_unordered(watermark: str) -> str:
    tokens = re.findall(r'\w+', watermark)
    pattern = ''.join('(?=.*' + re.escape(token) + ')' for token in tokens)
    return pattern


def debug_substitution(content: str, watermark: str, threshold=80) -> str:
    # Match complete lines with a text-showing operator: ( ... )Tj
    full_pattern = r'(^\s*\()(.*)(\)\s*Tj\s*$)'

    def replacement(match: re.Match) -> str:
        inner_text = match.group(2)

        # if fuzz.partial_ratio(watermark, inner_text) >= threshold:
        #     print("FYI; Watermark:", watermark)
        #     print("FYI; Matching line:", match.group(0))

        if fuzz.ratio(watermark, inner_text) >= threshold:
            # Replace inner content with white space of the same length
            replaced_inner = " " * len(inner_text)
            new_line = match.group(1) + replaced_inner + match.group(3)
            print("Watermark:", watermark)
            print("Matching line:", match.group(0))
            print("Replacing with:", new_line)
            return new_line

        return match.group(0)

    new_content = re.sub(full_pattern, replacement, content, flags=re.MULTILINE)
    return new_content


def remove_watermarks(input_pdf: Path, output_pdf: Path, watermarks: list):
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        # Decompress the PDF to a temporary file (in QDF mode)
        temp_file = tmp.name

        subprocess.run(
            ["qpdf", "--qdf", "--object-streams=disable", str(input_pdf), temp_file],
            check=True,
        )

        # Read the decompressed content
        with open(temp_file, "r", encoding="latin1", newline="") as fd:
            content = fd.read()

        new_content = content

        # For each watermark, build a flexible regex that matches the entire line containing the watermark text
        for watermark in watermarks:
            new_content = debug_substitution(new_content, watermark)

        if new_content == content:
            raise NothingToDo()

        # Write back the modified content
        with open(temp_file, "w", encoding="latin1", newline="") as fd:
            fd.write(new_content)

        # Recompress the PDF
        subprocess.run(
            ["qpdf", "--object-streams=generate", temp_file, str(output_pdf)],
            check=True,
        )


def main(input_pdf: Path, output_pdf: Path):
    # Sanity checks: ensure the input file exists and is a file.
    if not input_pdf.exists() or not input_pdf.is_file():
        sys.exit(f"Error: Input file '{input_pdf}' does not exist or is not a valid file.")

    # Sanity check: avoid overwriting an existing output file.
    if output_pdf.exists():
        sys.exit(f"Error: Output file '{output_pdf}' already exists. Remove it or specify a different path.")

    # Extract watermark information from the first page text.
    text = extract_first_page_text(input_pdf)
    extract_watermarks(text)  # Assumes 'watermarks' is a global list populated by this call.

    # Remove watermarks from the PDF.
    remove_watermarks(input_pdf, output_pdf, watermarks_found)
    print(f"Watermark removed. Cleaned file saved as: {output_pdf}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Remove watermarks from a PDF file using fuzzy matching and QDF mode."
    )
    parser.add_argument(
        "input_pdf",
        type=Path,
        help="Path to the input PDF file"
    )
    parser.add_argument(
        "output_pdf",
        type=Path,
        nargs='?',
        help="Path to the output PDF file. If not provided, '-dry.pdf' will be appended to the input filename."
    )
    args = parser.parse_args()

    input_pdf: Path = args.input_pdf

    # If output_pdf is not provided, append '-dry.pdf' to the input filename.
    output_pdf = args.output_pdf if args.output_pdf else input_pdf.with_name(input_pdf.name + "-dry.pdf")

    try:
        main(input_pdf, output_pdf)
    except NothingToDo:
        print("No watermarks found in the input file. No changes made.")
        exit(0)

    if not args.output_pdf:
        retirement_dir = input_pdf.parent / "_retired"
        retirement_dir.mkdir(exist_ok=True)

        input_pdf.rename(retirement_dir / f"{input_pdf.name}_(retired at {datetime.now().strftime('%Y%m%d-%H%M%S')})")

        output_pdf.rename(input_pdf)
