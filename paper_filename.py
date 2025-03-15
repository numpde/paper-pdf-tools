import os
import sys
import json
import logging
import fitz
import openai
import dotenv
import argparse

from pathlib import Path
from utils import function_to_schema

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# Exceptions for tool calls
class FinishToolCalls(Exception):
    pass

# Global variable to store the generated filename
filename_result = None

# Initialize OpenAI client similar to the original script
dotenv.load_dotenv()
client = openai.Client(api_key=os.environ["OPENAI_API_KEY"])

# Tool functions
def tool_set_filename(year: int, author_name_list: list[str], title: str):
    global filename_result

    if isinstance(author_name_list, str):
        author_name_list = [author_name_list]

    # Remove dashes and apostrophes from each author name
    cleaned_authors = [name.replace("-", "").replace("'", "") for name in author_name_list]
    # Apply author formatting rules: if more than 3 authors, list only first two and final
    if len(cleaned_authors) > 3:
        authors_str = f"{cleaned_authors[0]}-{cleaned_authors[1]}-...-{cleaned_authors[-1]}"
    else:
        authors_str = "-".join(cleaned_authors)
    # Replace colon with " -- " in title
    processed_title = title.replace(": ", " -- ")
    # Construct the filename
    filename_result = f"{year}-{authors_str} ({processed_title})"
    logging.info(f"Tool 'tool_set_filename' called with year: {year}, author_name_list: {author_name_list}, title: {title}.")
    logging.info(f"Constructed filename: {filename_result}")
    return f"Filename set: {filename_result}"

def tool_finished():
    logging.info("Tool 'tool_finished' called. Finishing tool calls.")
    raise FinishToolCalls()

def execute_tool_call(tool_call, tools_map):
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    logging.info(f"Executing tool call: {name}({args})")
    return tools_map[name](**args)

def run_full_turn(system_message, tools, messages):
    num_init_messages = len(messages)
    messages = messages.copy()

    while True:
        tool_schemas = [function_to_schema(tool) for tool in tools]
        tools_map = {tool.__name__: tool for tool in tools}

        logging.info("Sending request to OpenAI with messages and tool schemas.")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_message}] + messages,
            tools=tool_schemas or None,
        )
        message = response.choices[0].message
        messages.append(message)
        if message.content:
            logging.info(f"Assistant response: {message.content}")

        # Check for tool calls in the response
        if not getattr(message, "tool_calls", None):
            logging.info("No tool calls detected. Exiting loop.")
            break

        for tool_call in message.tool_calls:
            result = execute_tool_call(tool_call, tools_map)
            logging.info(f"Tool call result: {result}")
            result_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            }
            messages.append(result_message)
    return messages[num_init_messages:]

def extract_first_page_text(pdf_path: Path) -> str:
    logging.info(f"Extracting text from the first page of: {pdf_path}")
    with fitz.open(str(pdf_path)) as doc:
        text = doc[0].get_text("text") if doc.page_count > 0 else ""
    logging.info("Extraction complete.")
    return text

def get_new_filename(first_page_text: str) -> str:
    global filename_result
    filename_result = None

    with Path(__file__).with_suffix(".prompt.txt").open(mode='r') as fd:
        prompt = fd.read().strip()
        prompt = prompt.replace("{first_page_text}", first_page_text)

    messages = [
        {"role": "system", "content": "You construct filenames for scientific paper PDFs."},
        {"role": "user", "content": prompt}
    ]
    tools = [tool_set_filename, tool_finished]

    logging.info("Starting tool-based filename generation.")
    try:
        run_full_turn("Filename generation", tools, messages)
    except FinishToolCalls:
        logging.info("Finished processing tool calls for filename generation.")

    if filename_result is None:
        sys.exit("Error: No filename was generated.")
    logging.info(f"Generated filename: {filename_result}")
    return filename_result

def main(input_pdf: Path):
    if not input_pdf.exists() or not input_pdf.is_file():
        sys.exit(f"Error: Input file '{input_pdf}' does not exist or is not a file.")

    first_page_text = extract_first_page_text(input_pdf)
    if not first_page_text.strip():
        sys.exit("Error: The first page contains no extractable text.")

    new_filename = get_new_filename(first_page_text)
    if not new_filename.lower().endswith('.pdf'):
        new_filename += '.pdf'

    new_file_path = input_pdf.with_name(new_filename)
    if new_file_path.exists():
        sys.exit(f"Error: Target file '{new_file_path}' already exists.")

    logging.info(f"Renaming file {input_pdf} to {new_file_path}")
    os.rename(input_pdf, new_file_path)
    logging.info(f"File renamed successfully to: {new_file_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Rename a scientific paper PDF using its first page content for OpenAI filename generation."
    )
    parser.add_argument("input_pdf", type=Path, help="Path to the input PDF file")
    args = parser.parse_args()
    main(args.input_pdf)
