from typing import Any

from .mangascandotws import MangaScanDotWS


class ScanFRDotOrg(MangaScanDotWS):
    name = "Scan FR"
    url = _base_url = "https://www.scan-fr.org/"

    _script_selector = "body > script:nth-child(10)"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._images_url = "https://opfrcdn.xyz/uploads/manga/"
