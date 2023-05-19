import re
from urllib.parse import urljoin

from sources.scans.mangascandotws import MangaScanDotWS


class ScanMangaVFDotWS(MangaScanDotWS):
    name = "scanmanga-vf.ws"

    _base_url = "https://scanmanga-vf.ws/"
    _rss_url = urljoin(_base_url, "feed")
    _images_url = "https://scansmangas.me/scans/"
    _search_url = urljoin(_base_url, "search")

    _link_scrap_reg = re.compile(
        r"https://scanmanga-vf.ws/manga/"
        r"(?P<manga_name>[\w\-.]+)/"
        r"(?P<chapter>(?P<number>\d+)(?:\.(?P<sub_number>\d+))?)"
    )
