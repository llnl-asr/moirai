// The Python binding of moirai's C++ actors: moirai._moirai, and
// moirai._moirai_dbg from the _dbg build (MOIRAI_PY_MODULE). The Python API
// (python/moirai) is built on it.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <memory>
#include <moirai/moirai.hpp>
#include <string>

#ifndef MOIRAI_PY_MODULE
#define MOIRAI_PY_MODULE _moirai
#endif

namespace py = pybind11;

namespace {
// An Activity Python ends deterministically (with / end()), not when it is
// collected. Keeps its name alive for dftracer, which holds a pointer.
class PyActivity {
  std::string name_;
  std::unique_ptr<moirai::Activity> activity_;

 public:
  explicit PyActivity(std::string name)
      : name_(std::move(name)),
        activity_(std::make_unique<moirai::Activity>(name_.c_str())) {}
  void relate(moirai::Relation relation, const moirai::Entity& entity) {
    if (activity_) activity_->relate(relation, entity);
  }
  moirai::Entity relate_entity(moirai::Relation relation,
                               const std::string& type, const std::string& key,
                               moirai::Store store, const std::string& uri) {
    if (activity_) return activity_->relate(relation, type, key, store, uri);
    return moirai::Entity(type, key, store, uri);
  }
  void end() { activity_.reset(); }
  bool active() const { return activity_ != nullptr; }
  const std::string& name() const { return name_; }
};
}  // namespace

// Types are module_local: _moirai and _moirai_dbg each register their own,
// as dftracer's bindings do.
PYBIND11_MODULE(MOIRAI_PY_MODULE, m) {
  m.doc() = "moirai: data provenance traced by dftracer (C++ binding)";
  m.attr("LAYER") = MOIRAI_LAYER;
  m.attr("CATEGORY") = MOIRAI_CATEGORY;
  m.attr("DEFAULT_TRACE_IO") = MOIRAI_DEFAULT_TRACE_IO != 0;
  m.attr("HAS_HDF5") = MOIRAI_HAS_HDF5 != 0;
  m.attr("HAS_MPI") = MOIRAI_HAS_MPI != 0;

  py::enum_<MoiraiStore>(m, "Store", py::module_local())
      .value("MEMORY", MOIRAI_STORE_MEMORY)
      .value("GPU_MEMORY", MOIRAI_STORE_GPU_MEMORY)
      .value("LOCAL_DISK", MOIRAI_STORE_LOCAL_DISK)
      .value("PARALLEL_FS", MOIRAI_STORE_PARALLEL_FS)
      .value("BURST_BUFFER", MOIRAI_STORE_BURST_BUFFER)
      .value("OBJECT_STORE", MOIRAI_STORE_OBJECT_STORE)
      .value("DATABASE", MOIRAI_STORE_DATABASE)
      .value("NETWORK", MOIRAI_STORE_NETWORK)
      .value("OTHER", MOIRAI_STORE_OTHER);
  py::enum_<MoiraiRole>(m, "Role", py::module_local())
      .value("UNKNOWN", MOIRAI_ROLE_UNKNOWN)
      .value("INPUT", MOIRAI_ROLE_INPUT)
      .value("OUTPUT", MOIRAI_ROLE_OUTPUT)
      .value("INTERMEDIATE", MOIRAI_ROLE_INTERMEDIATE)
      .value("PARAMETER", MOIRAI_ROLE_PARAMETER)
      .value("REFERENCE", MOIRAI_ROLE_REFERENCE);
  py::enum_<MoiraiRelation>(m, "Relation", py::module_local())
      .value("USED", MOIRAI_REL_USED)
      .value("GENERATED", MOIRAI_REL_GENERATED)
      .value("INVALIDATED", MOIRAI_REL_INVALIDATED)
      .value("UPDATED", MOIRAI_REL_UPDATED)
      .value("DERIVED_FROM", MOIRAI_REL_DERIVED_FROM)
      .value("REVISION_OF", MOIRAI_REL_REVISION_OF)
      .value("CONTAINS", MOIRAI_REL_CONTAINS)
      .value("PART_OF", MOIRAI_REL_PART_OF)
      .value("SPECIALIZATION_OF", MOIRAI_REL_SPECIALIZATION_OF)
      .value("ALTERNATE_OF", MOIRAI_REL_ALTERNATE_OF)
      .value("DEPENDS_ON", MOIRAI_REL_DEPENDS_ON);

  m.def("initialize", &moirai::initialize, py::arg("log_file") = "",
        "Configure dftracer for provenance and start tracing");
  m.def("finalize", &moirai::finalize, "Stop tracing and flush");
  m.def("is_active", &moirai::is_active);
  m.def(
      "relation_name",
      [](MoiraiRelation r) { return std::string(moirai_relation_name(r)); },
      py::arg("relation"));

  py::class_<moirai::EntityType>(m, "EntityType", py::module_local())
      .def(py::init<const std::string&, moirai::Role, const std::string&>(),
           py::arg("name"), py::arg("role"), py::arg("description") = "")
      .def_property_readonly("name", &moirai::EntityType::name);
  py::class_<moirai::Entity>(m, "Entity", py::module_local())
      .def(py::init<const std::string&, const std::string&, moirai::Store,
                    const std::string&>(),
           py::arg("type"), py::arg("key"),
           py::arg("store") = MOIRAI_STORE_MEMORY, py::arg("uri") = "")
      .def(py::init<moirai::Id>(), py::arg("id"))
      .def_property_readonly("id", &moirai::Entity::id)
      .def("relate", &moirai::Entity::relate, py::arg("relation"),
           py::arg("object"))
      .def("__int__", &moirai::Entity::id)
      .def("__eq__", [](const moirai::Entity& a,
                        const moirai::Entity& b) { return a.id() == b.id(); })
      .def("__hash__", &moirai::Entity::id)
      .def("__repr__", [](const moirai::Entity& e) {
        char hex[MOIRAI_HEX_LEN];
        moirai_hex(e.id(), hex);
        return std::string("Entity(") + hex + ")";
      });
  py::class_<PyActivity>(m, "Activity", py::module_local())
      .def(py::init<std::string>(), py::arg("name"))
      .def("relate", &PyActivity::relate, py::arg("relation"),
           py::arg("entity"))
      .def("relate_entity", &PyActivity::relate_entity, py::arg("relation"),
           py::arg("type"), py::arg("key"),
           py::arg("store") = MOIRAI_STORE_MEMORY, py::arg("uri") = "")
      .def("end", &PyActivity::end)
      .def_property_readonly("active", &PyActivity::active)
      .def_property_readonly("name", &PyActivity::name);
}
