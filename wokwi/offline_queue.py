# Simple file-backed queue for when the pico loses internet connection

# Stores items line by line separated by tabs

class OfflineQueue:
    def __init__(self, filename, max_items=100):
        self.filename = filename
        self.max_items = int(max_items)
        self.items = []
        self._load()

    def _load(self):
        self.items = []
        try:
            with open(self.filename, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.items.append(line)
# File probably doesn't exist yet, which is totally fine on first boot
        except OSError:
            pass
        self.items = self.items[-self.max_items:]
# just keep the latest items if it exceeds max size

    def _rewrite(self):
        with open(self.filename, "w") as f:
            for item in self.items:
                f.write(item + "\n")
# Rewrites the whole file. Not super efficient for flash wear, 
# but keeps things simple for our queue size.

    def add(self, topic, payload, qos=1, retain=False):
         # packing everything into a single tab-separated line
        record = "{}\t{}\t{}\t{}".format(
            topic,
            int(qos),
            1 if retain else 0,
            payload,
        )
        self.items.append(record)
        self.items = self.items[-self.max_items:]
        self._rewrite()
# trim if we go over the limit

    def count(self):
        return len(self.items)

    def flush(self, publisher):
        sent = 0
        while self.items:
            record = self.items[0]
# loop through and try to publish everything we missed
            try:
# split back out into parts
                topic, qos, retain, payload = record.split("\t", 3)
                publisher(
                    topic,
                    payload,
                    int(qos),
                    retain == "1",
                )
 # if publishing fails, stop flushing right here
            except Exception:
                break
            self.items.pop(0)
            sent += 1
            self._rewrite()
        return sent
