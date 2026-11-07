# hpc/apptainer

Apptainer definition on the same CUDA base as `.devcontainer/cuda`. It installs uv; the project
itself is bound in at run time, so the image does not go stale.

```
apptainer build alea.sif hpc/apptainer/alea.def      # from the repo root
apptainer run --nv --bind "$PWD:/work" --pwd /work alea.sif --config conf/study/brev72.yaml
```

`--nv` exposes the host NVIDIA driver. The first run syncs the venv with `uv sync
--all-extras --group dev`: run that once inside the container if the node has no network
(`apptainer exec --nv ... uv sync ...`). Untested on a real cluster.

**Roadmap phase:** 1 (landed in PR 7)
