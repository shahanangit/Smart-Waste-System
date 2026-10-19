import config

 # TODO: double verify if we need to add a 'compost' bin mapping later 
 # team said something about putting brown dumpsters next race


BIN_TO_LABEL = {
    "yellow": "recycled",
    "green": "green",
    "red": "landfill",
}
# Quick workaround because config.SORT_ANGLES can be a dict or whatever else, let's just make it a set of keys like normal.

ALLOWED_LABELS = set(config.SORT_ANGLES.keys())


class EventValidator:
    def __init__(self, seen_limit=100):
        self.seen_limit = int(seen_limit)
        self.seen_ids = []

    def _remember(self, identity):
        self.seen_ids.append(identity)
        if len(self.seen_ids) > self.seen_limit:
            self.seen_ids.pop(0)

    def _is_duplicate(self, identity):
        return identity in self.seen_ids

    def validate(self, event):
        version = event.get("schema_version")

        # handling schema versions as they come in

        if version == 1:
            return self._validate_v1(event)

        if version == 2:
            return self._validate_v2(event)

        raise ValueError("unsupported schema_version")

    def _validate_v1(self, event):
        if event.get("bin_id") != config.DEVICE_ID:
            raise ValueError("wrong bin_id")

        label = event.get("label")

         # check device ID matches ours

        if label not in ALLOWED_LABELS:
            raise ValueError("unknown label")

# verifying confidence (python isinstance(True, int) returns True, so need to explicitly block bools again)

        confidence = event.get("confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not config.CLASSIFIER_MIN_CONFIDENCE <= confidence <= 1.0
        ):
            raise ValueError("confidence")

        identity = event.get("event_id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("event_id")

        if self._is_duplicate(identity):
            raise DuplicateEvent(identity)

        self._remember(identity)

            # returning a normalized dict structure 

        return {
            "identity": identity,
            "schema_version": 1,
            "label": label,
            "confidence": confidence,
            "source": event.get("source"),
            "timestamp": event.get("timestamp"),
            "raw": event,
        }

    def _validate_v2(self, event):
        if event.get("message_type") != "waste_classification":
            raise ValueError("message_type")

        confidence = event.get("confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not config.CLASSIFIER_MIN_CONFIDENCE <= confidence <= 1.0
        ):
            raise ValueError("confidence")

        bin_name = event.get("bin")

        # e-waste or null intentionally causes no kerbside servo movement.

        if bin_name not in BIN_TO_LABEL:
            raise ValueError("unsupported/non-kerbside bin")

        label = BIN_TO_LABEL[bin_name]

        device_id = event.get("device_id")
        sequence = event.get("sequence")

        if not isinstance(device_id, str) or not device_id:
            raise ValueError("device_id")
        if not isinstance(sequence, int):
            raise ValueError("sequence")

        identity = "{}:{}".format(device_id, sequence)

        if self._is_duplicate(identity):
            raise DuplicateEvent(identity)

        self._remember(identity)

        return {
            "identity": identity,
            "schema_version": 2,
            "label": label,
            "confidence": confidence,
            "source": event.get("source"),
            "timestamp": event.get("timestamp"),
            "classification": event.get("classification"),
            "bin": bin_name,
            "pipeline": event.get("pipeline"),
            "raw": event,
        }


class DuplicateEvent(Exception):
    pass
