# Argon2id Parameters

Algorithm: **Argon2id** (hybrid, resistant to both side-channel and GPU attacks)
Library: `argon2-cffi`

## Chosen parameters

| Parameter | Value | Rationale |
|---|---|---|
| `time_cost` | 2 | Iterations |
| `memory_cost` | 65536 | 64 MB RAM per hash |
| `parallelism` | 2 | Matches 2-core dev container |
| `hash_len` | 32 | 256-bit output |
| `salt_len` | 16 | 128-bit random salt |

## Benchmark (dev container — 2 vCPU / 2 GB RAM)

Target: ~200–500 ms per hash on the deployment server.
Measure with:

```bash
python -c "
import time
from argon2 import PasswordHasher
ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)
start = time.perf_counter()
for _ in range(10):
    ph.hash('BenchmarkPassword123!')
print(f'{(time.perf_counter() - start) / 10 * 1000:.1f} ms/hash')
"
```

## Production guidance

Before deploying to production, re-run the benchmark on the actual server hardware and adjust
`memory_cost` and `time_cost` so that a single hash takes 200–500 ms.
Update this file with the production parameters and redeploy.

OWASP recommends: m=47104 (46 MB), t=1, p=1 as a minimum baseline for Argon2id.
Our parameters exceed this baseline.
