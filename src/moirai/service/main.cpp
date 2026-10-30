// moirai-service <start|stop>: dftracer_service for moirai (MoiraiService).
// Start it with the application's MOIRAI_LOG_FILE (and MOIRAI_SERVICE_SHM)
// before the application, stop it after.
#include <moirai/core/common/logging.h>
#include <moirai/core/common/singleton.h>
#include <moirai/service/moirai_service.h>

#include <cstdio>
#include <cstring>

int main(int argc, char* argv[]) {
  if (argc != 2 || (std::strcmp(argv[1], "start") != 0 &&
                    std::strcmp(argv[1], "stop") != 0)) {
    std::fprintf(stderr,
                 "Usage: %s <start|stop>\n"
                 "Runs dftracer_service for moirai: MOIRAI_LOG_FILE is the "
                 "trace prefix the application uses, MOIRAI_SERVICE_SHM its "
                 "ring; MOIRAI_DFTRACER_SERVICE overrides the service binary "
                 "(%s).\n",
                 argv[0], MOIRAI_DFTRACER_SERVICE_PATH);
    return 2;
  }
  MOIRAI_LOGGER_INIT();
  moirai::MoiraiService service(
      moirai::Singleton<moirai::ConfigurationManager>::get_instance());
  const int rc = service.run(argv[1]);
  std::fprintf(stderr, "%s: cannot run %s\n", argv[0],
               service.binary().c_str());
  return rc;
}
