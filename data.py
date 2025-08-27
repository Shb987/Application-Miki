import os

def get_tree_lines(root, prefix=""):
    """Generate directory structure lines recursively."""
    lines = []
    contents = sorted(os.listdir(root))
    pointers = ['├── '] * (len(contents) - 1) + ['└── ']

    for pointer, item in zip(pointers, contents):
        path = os.path.join(root, item)
        lines.append(prefix + pointer + item)
        if os.path.isdir(path):
            extension = "│   " if pointer == '├── ' else "    "
            lines.extend(get_tree_lines(path, prefix + extension))
    return lines
# Example usage: pass your project root directory path here
project_root = "new"  # Change this to your actual root path
# print(project_root)
# print_tree(project_root)
lines = [project_root] + get_tree_lines(project_root)

with open("folder_structure.txt", "w", encoding="utf-8") as f:
    for line in lines:
        f.write(line + "\n")

print("Folder structure saved to folder_structure.txt")