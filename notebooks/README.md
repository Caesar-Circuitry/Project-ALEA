# notebooks

Exploration and EP charts. Notebooks import `alea` and hold no core logic. Each .ipynb is paired with a jupytext .py script; outputs are stripped on commit.

**Roadmap phase:** 1+

The `.py` (jupytext percent format) is the committed source of truth; `.ipynb` files are git-ignored. Open the `.py` in JupyterLab with "Open With > Notebook", or run `jupytext --to ipynb notebooks/01_cpu_heatmap.py`.

- `01_cpu_heatmap.py`: CPU study on the normal robot with a tiny shot count, then the heat map.
- `02_study_results.py`: loads `results/study` (or runs a tiny 4-condition CPU study), shows the effects table, the worst/best conditions and the worst heat map.
