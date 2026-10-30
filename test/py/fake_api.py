"""A stand-in for moirai's API, enough for moirai.agent.recorder, so that the
pure-Python parts of the agent can be tested without the native module."""
import types


class _Entity:
    def __init__(self, api, id):
        self.id = id
        self.api = api

    def __int__(self):
        return self.id

    def relate(self, relation, other):
        self.api.relations.append((self.id, relation, int(other)))


class _Activity:
    def __init__(self, api, name):
        self.api, self.name, self.args = api, name, {"relations": []}

    def begin(self):
        return self

    def span(self, start, end):
        self.args.update(start_us=start, end_us=end)

    def relate(self, relation, entity):
        self.args["relations"].append((relation, int(entity)))

    def end(self):
        self.api.activities.append(self)


class FakeAPI:
    def __init__(self, redact="", sensitive_paths=""):
        self.entities, self.activities, self.relations = {}, [], []
        self.artifacts = []
        self.Role = types.SimpleNamespace(PARAMETER="P", INPUT="I",
                                          INTERMEDIATE="M")
        self.Store = types.SimpleNamespace(DATABASE="db", PARALLEL_FS="pfs")
        self.Relation = types.SimpleNamespace(
            USED="used", GENERATED="generated", UPDATED="updated",
            PART_OF="part_of", DERIVED_FROM="derived", REVISION_OF="revision")
        self.Lifetime = types.SimpleNamespace(TRANSIENT=0, PERSISTENT=1)
        self._conf = types.SimpleNamespace(
            redact=redact, sensitive_paths=sensitive_paths, dir="", settings=[])

    def agent_configuration(self):
        return self._conf

    def entity_type(self, *args):
        pass

    def entity(self, type, key, store, uri):
        # Stable 64-bit id from the key, as moirai's.
        id = (hash((type, key)) & 0xFFFFFFFFFFFFFFF) | 1
        self.entities[id] = (type, key, uri)
        return _Entity(self, id)

    def Entity(self, id):
        return _Entity(self, id)

    def Activity(self, name):
        return _Activity(self, name)

    def store_artifact(self, text):
        self.artifacts.append(text)
        return types.SimpleNamespace(
            uri=f"artifact://{len(self.artifacts):016x}")

    def store_artifact_file(self, path, lifetime):
        with open(path, errors="replace") as fh:
            return self.store_artifact(fh.read())
