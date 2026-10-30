# moirai

moirai records data provenance for HPC applications -- the entities an
application works with, what each activity used, generated, invalidated or
updated, and how entities relate -- in C, C++ and Python. It runs
[dftracer](https://github.com/llnl-asr/dftracer) underneath it, configured
for provenance: always through `dftracer_service` (producer/consumer mode),
with I/O tracing on or off, and HDF5/MPI passed down at build time.

```cpp
#include <moirai/moirai.hpp>

moirai::initialize();
moirai::Entity in0("dataset", "in0", MOIRAI_STORE_PARALLEL_FS, "file:///data/in0.h5");
{
  moirai::Activity train("train");
  train.used(in0);
  train.generates("model", "m0");
}
moirai::finalize();
```

```bash
cmake -S . -B build -DCMAKE_PREFIX_PATH=<dftracer prefix> -DMOIRAI_ENABLE_TESTS=ON
cmake --build build -j && (cd build && ctest)

export MOIRAI_LOG_FILE=$PWD/traces/run1
moirai-service start && ./my_app && moirai-service stop
```

Documentation: [docs/](docs/) (Read the Docs; `make -C docs html`).

## License

moirai is distributed under the terms of the MIT license.
All new contributions must be made under this license.

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for details.

SPDX-License-Identifier: MIT

LLNL-CODE-2024514 — Applied Storage Research (ASR)
