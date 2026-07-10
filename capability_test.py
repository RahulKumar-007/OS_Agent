# !/usr/bin/env python3
import requests
import json
import os
import shutil # For directory removal
import subprocess # For initial file creation if needed, though os.makedirs/open is better

# --- Configuration ---
BASE_URL = "http://localhost:8000/api"
# Use a dedicated directory in /tmp for cleaner testing.
# Ensure this directory is writable by the user running the script.
TEST_DIR = "/tmp/aegis_test_env"
DUMMY_TEXT_FILE = os.path.join(TEST_DIR, "aegis_test_file.txt")
DUMMY_DOC_FILE = os.path.join(TEST_DIR, "aegis_document.txt") # Placeholder for document processing test
DUMMY_IMG_FILE = os.path.join(TEST_DIR, "aegis_image.jpg")   # Placeholder for image OCR test
NEW_FILE_PATH = os.path.join(TEST_DIR, "aegis_created_file.txt")
NEW_DIR_PATH = os.path.join(TEST_DIR, "aegis_new_dir")
COPY_FILE_PATH = os.path.join(TEST_DIR, "aegis_copied_file.txt")
# Path AFTER moving a file into NEW_DIR_PATH, and possibly renaming it.
# We'll move COPY_FILE_PATH into NEW_DIR_PATH and call it 'aegis_moved_file_to_new_dir.txt'
MOVED_FILE_DESTINATION_PATH = os.path.join(NEW_DIR_PATH, "aegis_moved_file_to_new_dir.txt")
RENAMED_FILE_PATH = os.path.join(NEW_DIR_PATH, "aegis_renamed_after_move.txt")


# --- Helper Functions ---
def make_request(method, endpoint, **kwargs):
    """Makes an API request and returns JSON response or error details."""
    url = f"{BASE_URL}/{endpoint}"
    print(f"-> Making {method} request to {url}")
    if 'json' in kwargs:
        print(f"   Payload: {kwargs['json']}")
    if 'params' in kwargs:
        print(f"   Params: {kwargs['params']}")

    try:
        response = requests.request(method, url, **kwargs, timeout=10) # Added timeout
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        print(f"<- Status Code: {response.status_code}")
        return response.json()
    except requests.exceptions.ConnectionError as e:
        print(f"Error: Could not connect to AEGIS backend at {url}. Is it running? Details: {e}")
        return {"error": f"Connection Error: {e}"}
    except requests.exceptions.Timeout:
        print(f"Error: Request timed out for {url}.")
        return {"error": "Request Timeout"}
    except requests.exceptions.RequestException as e:
        print(f"Error during request to {url}: {e}")
        # Attempt to return error details from response body if available
        try:
            error_details = response.json()
            print(f"<- Status Code: {response.status_code}")
            print(f"   Error Details: {error_details}")
            return error_details
        except (json.JSONDecodeError, AttributeError):
            print(f"<- Status Code: {response.status_code}")
            return {"error": str(e), "status_code": response.status_code if 'response' in locals() else None}
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {"error": str(e)}

def create_dummy_files_and_dirs():
    """Creates prerequisite files and directories for testing."""
    print(f"\n--- Creating test environment in {TEST_DIR} ---")
    try:
        os.makedirs(TEST_DIR, exist_ok=True)
        os.makedirs(NEW_DIR_PATH, exist_ok=True)

        # Create a dummy text file for file operations and content search
        with open(DUMMY_TEXT_FILE, "w") as f:
            f.write("This is a test file for AEGIS capabilities.\nIt contains multiple lines for searching.\nAEGIS can find content within this file.\n")
        print(f"Created: {DUMMY_TEXT_FILE}")

        # Create a dummy file for document summarization test
        with open(DUMMY_DOC_FILE, "w") as f:
            f.write("This is a sample document to test summarization. It has some content.\nAEGIS should be able to summarize this text effectively.\nWe are testing the document understanding capabilities here.\nThis file has several sentences to ensure summarization works.\n")
        print(f"Created: {DUMMY_DOC_FILE}")

        # Create a placeholder for an image file for OCR test
        # In a real scenario, this would be an actual image file (e.g., .png, .jpg).
        # For this script, we'll create an empty file and note the dependency.
        # AEGIS might expect a valid image file for OCR to succeed.
        with open(DUMMY_IMG_FILE, "w") as f:
            pass
        print(f"Created placeholder: {DUMMY_IMG_FILE} (Note: AI/OCR tools expect actual image files)")

    except OSError as e:
        print(f"Failed to create test environment: {e}")
        print("Please check permissions or if the directory is in use.")
        exit(1) # Exit if setup fails

def cleanup_test_environment():
    """Cleans up the created files and directories."""
    print(f"\n--- Cleaning up test environment: {TEST_DIR} ---")
    if os.path.exists(TEST_DIR):
        try:
            shutil.rmtree(TEST_DIR)
            print(f"Removed directory: {TEST_DIR}")
        except OSError as e:
            print(f"Error removing directory {TEST_DIR}: {e}")
    else:
        print(f"Test environment directory {TEST_DIR} not found, skipping cleanup.")

# --- Test Case Functions ---

def test_chat_agent():
    print("\n--- Testing: Chat Agent (text input -> plan/response) ---")
    message_text_query = "What is AEGIS?"
    print(f"Sending chat message: '{message_text_query}'")
    response = make_request("POST", "chat", json={"message": message_text_query})
    print(f"Chat Agent Response:\n{json.dumps(response, indent=2)}\n")
    # Note: The response might be a plan, an answer, or a request for clarification.

def test_file_operations_browse_preview():
    print("\n--- Testing: File Operations (Browse & Preview) ---")
    # List test directory contents
    print(f"Browsing directory: {TEST_DIR}")
    response = make_request("GET", "browse", params={"path": TEST_DIR})
    print(f"Browse Response:\n{json.dumps(response, indent=2)}\n")

    # Preview file content
    print(f"Previewing content of: {DUMMY_TEXT_FILE}")
    response = make_request("GET", "preview", params={"path": DUMMY_TEXT_FILE})
    print(f"Preview Response:\n{json.dumps(response, indent=2)}\n")

def test_file_operations_create_delete():
    print("\n--- Testing: File Operations (Create & Delete) ---")
    # Create a new file
    print(f"Creating new file: {NEW_FILE_PATH}")
    file_content = "This file was created by the test script for deletion test."
    response = make_request("POST", "fileop/create-file", json={"path": NEW_FILE_PATH, "content": file_content})
    print(f"Create File Response:\n{json.dumps(response, indent=2)}\n")

    # Create a new directory
    print(f"Creating new directory: {NEW_DIR_PATH}")
    response = make_request("POST", "fileop/create-folder", json={"path": NEW_DIR_PATH})
    print(f"Create Folder Response:\n{json.dumps(response, indent=2)}\n")

    # Delete the newly created file
    print(f"Deleting file: {NEW_FILE_PATH}")
    response = make_request("POST", "fileop/delete", json={"path": NEW_FILE_PATH})
    print(f"Delete File Response:\n{json.dumps(response, indent=2)}\n")

def test_file_operations_move_copy_rename():
    print("\n--- Testing: File Operations (Copy, Move, Rename) ---")
    # Copy the dummy text file to a new location
    print(f"Copying {DUMMY_TEXT_FILE} to {COPY_FILE_PATH}")
    response = make_request("POST", "fileop/copy", json={"source": DUMMY_TEXT_FILE, "destination": COPY_FILE_PATH})
    print(f"Copy Response:\n{json.dumps(response, indent=2)}\n")

    # Move the copied file into the newly created directory and rename it
    print(f"Moving and renaming {COPY_FILE_PATH} to {MOVED_FILE_DESTINATION_PATH}")
    response = make_request("POST", "fileop/move", json={"source": COPY_FILE_PATH, "destination": MOVED_FILE_DESTINATION_PATH})
    print(f"Move/Rename Response:\n{json.dumps(response, indent=2)}\n")

def test_file_operations_trash_restore():
    print("\n--- Testing: File Operations (Trash & Restore) ---")
    # Trash the file that was just moved and renamed
    print(f"Trashing file: {MOVED_FILE_DESTINATION_PATH}")
    response = make_request("POST", "fileop/trash", json={"path": MOVED_FILE_DESTINATION_PATH})
    print(f"Trash Response:\n{json.dumps(response, indent=2)}\n")

    # Restore the trashed file
    # Note: The path for restore might be the original path or based on how trash is implemented by AEGIS.
    # We assume restoring by the path it was moved to prior to trashing.
    print(f"Restoring file from trash: {MOVED_FILE_DESTINATION_PATH}")
    response = make_request("POST", "fileop/restore", json={"path": MOVED_FILE_DESTINATION_PATH})
    print(f"Restore Response:\n{json.dumps(response, indent=2)}\n")

def test_search_capabilities():
    print("\n--- Testing: Search Capabilities ---")
    # Search by content in created files
    print(f"Searching for 'test file' in *.txt files in {TEST_DIR}")
    response = make_request("POST", "search/content", json={"query": "test file", "include": "*.txt", "path": TEST_DIR})
    print(f"Search Content Response:\n{json.dumps(response, indent=2)}\n")

    # Indexed Search
    # Note: This capability depends on the background indexer running and having indexed TEST_DIR.
    # It might fail if the index is not ready or does not contain content from /tmp.
    print(f"Performing indexed search for 'AEGIS' (Requires indexer to be active and potentially have indexed {TEST_DIR})")
    response = make_request("GET", "index/search", params={"query": "AEGIS"})
    print(f"Indexed Search Response:\n{json.dumps(response, indent=2)}\n")

def test_document_ai_capabilities():
    print("\n--- Testing: Document & Image AI Capabilities ---")

    # Summarize document
    print(f"Attempting to summarize document: {DUMMY_DOC_FILE}")
    response = make_request("POST", "summarize_document", json={"path": DUMMY_DOC_FILE})
    print(f"Summarize Document Response:\n{json.dumps(response, indent=2)}\n")
    # Note: This assumes the backend can process .txt as a document and the summarization tool is functional.

    # OCR Image
    print(f"Attempting OCR on image: {DUMMY_IMG_FILE}")
    response = make_request("POST", "ocr_image", json={"path": DUMMY_IMG_FILE})
    print(f"OCR Image Response:\n{json.dumps(response, indent=2)}\n")
    # Note: This assumes DUMMY_IMG_FILE is a valid image format recognized by the OCR tool.
    # An empty file will likely cause an error.

# --- Main Execution Block ---
if __name__ == "__main__":
    # Create prerequisite files and directories before running tests
    create_dummy_files_and_dirs()

    # Execute all test functions sequentially
    test_chat_agent()
    test_file_operations_browse_preview()
    test_file_operations_create_delete()
    test_file_operations_move_copy_rename()
    test_file_operations_trash_restore()
    test_search_capabilities()
    test_document_ai_capabilities()

    # Final cleanup of the test environment
    cleanup_test_environment()

    print("\n--- All AEGIS capability tests completed. ---")
    print("Review the output above for success/failure of each test.")
    print("Note on Git Integration:")
    print(" - Git capabilities are typically invoked via the Agent Executor as part of a plan, not direct API calls.")
    print(" - To test Git, ask AEGIS to perform a Git operation via chat (e.g., 'git status in my project').")
    print("\nNote on AI/Search Capabilities:")
    print(" - Success of AI/OCR/Indexed Search tests depends on background services being active and correctly configured.")
    print(" - Dummy files for AI tests (document/image) might lead to errors if AEGIS expects specific file formats or metadata.")
    print(" - Ensure AEGIS backend and its dependencies (LLM, indexer, etc.) are running.")
