# latex_merger.py
import os
import re

# Define regex to match \input or \include commands
# Matches \input{...}, \include{...}, \input{ ... }, etc.
# Captures the filename/path inside the curly braces

INPUT_REGEX = re.compile(r'\\(?:input|include)\s*\{([^}]+)\}')

def merge_latex_file(filepath, base_dir):
    """
    Recursively read and merge LaTeX file content.
    
    :param filepath: The path of the .tex file to process (relative to base_dir)
    :param base_dir: The root directory of the project
    :return: The merged file content string
    """
    
    # Construct the full system path of the file
    full_path = os.path.join(base_dir, filepath)
    
    # Ensure the file exists
    if not os.path.exists(full_path):
        # Try without .tex extension if it was added
        if filepath.endswith('.tex') and os.path.exists(full_path[:-4]):
            full_path = full_path[:-4]
        # Try adding .tex extension if it was missing
        elif not filepath.endswith('.tex') and os.path.exists(full_path + '.tex'):
             full_path = full_path + '.tex'
        else:
            # Fallback strategy 1: Recursive search
            # If the file is not found in the expected location, try to find it recursively in base_dir
            # This handles cases where relative paths are messy or main.tex is moved but paths not updated
            # or simply user error in LaTeX paths.
            
            # Extract just the filename
            target_filename = os.path.basename(filepath)
            # Remove extension for search if present, to be flexible
            if target_filename.endswith('.tex'):
                target_filename_no_ext = target_filename[:-4]
            else:
                target_filename_no_ext = target_filename
            
            found_path = None
            for root, dirs, files in os.walk(base_dir):
                for file in files:
                    if file == target_filename or file == target_filename_no_ext + '.tex':
                         found_path = os.path.join(root, file)
                         break
                if found_path: break
            
            if found_path:
                print(f"✅ Auto-corrected path: {filepath} -> {found_path}")
                full_path = found_path
                # Continue to read file content below
            else:
                print(f"⚠️ Warning: File not found - {full_path}")
                # return f"\\input{{{filepath}}}" # Keep original command if not found
                return "" # Return empty string to avoid processing errors later

    
    # Read file content
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {full_path}: {e}")
        return ""

    # Use sub method for replacement
    def replacer(match):
        # match.group(1) is the file path captured inside the curly braces
        included_file_path = match.group(1)
        
        # Try to fix relative paths: since paths in included files are usually relative to the main file,
        # we don't need complex path correction here because \input is always relative to base_dir (i.e., main file directory).
        
        # Recursively call merge_latex_file to process \input in included files
        print(f"✅ On Merge: {included_file_path}")
        
        # Ensure the included filename has .tex suffix, add if missing
        # if not included_file_path.endswith('.tex'):
        #    included_file_path += '.tex'
            
        merged_content = merge_latex_file(included_file_path, base_dir)
        
        # Add comments before and after included content for debugging and clarity
        comment_start = f"\n\n% --- START OF FILE: {included_file_path} ---\n"
        comment_end = f"\n% --- END OF FILE: {included_file_path} ---\n\n"
        
        return comment_start + merged_content + comment_end

    # Replace all matched \input/\include commands
    return INPUT_REGEX.sub(replacer, content)
