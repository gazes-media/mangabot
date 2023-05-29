from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Iterable

from bs4 import BeautifulSoup
from mediasub import Source
from mediasub.utils import normalize


@dataclass(kw_only=True)
class Webtoon:
    eid: int
    name: str
    author: str
    likes: str | None = None
    genre: str
    type: str
    url: str
    thumbnail: str | None = None
    description: str | None = None

    internal: Any = None

    @property
    def id(self) -> str:
        return f"WEBTOON/{self.eid}"


@dataclass(kw_only=True)
class WebtoonEpisode:
    webtoon: Webtoon
    name: str
    number: int
    language: str | None
    url: str

    internal: Any = None

    def __post_init__(self):
        self.db_identifier = f"{normalize(self.webtoon.name)}/{self.number}"


class WebtoonSource(Source["WebtoonEpisode"]):
    name = "Webtoons"
    url = _base_url = "https://www.webtoons.com/"

    _cookies = {"pagGDPR": "true"}

    _webtoon_url_ft = "https://www.webtoons.com/episodeList?titleNo={eid}"
    _canva_url_ft = "https://www.webtoons.com/challenge/episodeList?titleNo={eid}"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

    async def get_recent(self, limit: int = 25) -> Iterable[WebtoonEpisode]:
        return []

    async def search(self, query: str) -> list[Webtoon]:
        results: list[Webtoon] = []
        full_url = f"https://www.webtoons.com/fr/search?keyword={query}"
        req = await self.client.get(full_url, cookies=self._cookies)
        soup = BeautifulSoup(req.content, features="lxml")

        originals = soup.find("ul", {"class": "card_lst"})
        if originals is not None:
            for item in originals.findAll("li"):  # type: ignore
                eid = int(item.a["href"].split("?")[-1].split("=")[-1])  # type: ignore
                name = str(item.find("p", {"class": "subj"}).getText())  # type: ignore
                author = str(item.find("p", {"class": "author"}).getText())  # type: ignore
                likes = str(item.find("em", {"class": "grade_num"}).getText())  # type: ignore
                genre = str(item.find("span", {"class": "genre"}).getText())  # type: ignore
                results.append(
                    Webtoon(
                        name=name,
                        url=self._webtoon_url_ft.format(eid=eid),
                        eid=eid,
                        author=author,
                        likes=likes,
                        genre=genre,
                        type="o",
                    )
                )

        canvas = soup.find("div", {"class": "challenge_lst"})
        if canvas is not None and canvas.ul is not None:  # type: ignore
            canvas = canvas.ul  # type: ignore
            for item in canvas.findAll("li"):  # type: ignore
                eid = int(item.a["href"].split("?")[-1].split("=")[-1])  # type: ignore
                name = str(item.find("p", {"class": "subj"}).getText())  # type: ignore
                author = str(item.find("p", {"class": "author"}).getText())  # type: ignore
                genre = str(item.find("p", {"class": "genre"}).getText())  # type: ignore
                results.append(
                    Webtoon(
                        name=name,
                        url=self._canva_url_ft.format(eid=eid),
                        eid=eid,
                        author=author,
                        genre=genre,
                        type="c",
                    )
                )

        return results

    async def get_episodes(self, webtoon: Webtoon) -> Iterable[WebtoonEpisode]:
        raise NotImplementedError


# def get_img_urls(url, episode, eid):
#     full_url = f"{url}a/viewer?title_no={eid}&episode_no={episode}"
#     req = requests.get(full_url, cookies=COOKIES)
#     soup = BeautifulSoup(req.content, features="lxml")
#     content = soup.find("div", {"id": "content"})
#     imagelist = content.find("div", {"id": "_imageList"})
#     images = []
#     if imagelist is not None:
#         for img in imagelist.findAll("img", {"class": "_images"}):
#             images.append(img["data-url"])
#     return images, full_url


# def get_filetype(url):
#     if url.endswith("/"):
#         return url[:-1].split("/")[-1].split("?")[0].split(".")[-1]
#     else:
#         return url.split("/")[-1].split("?")[0].split(".")[-1]


# def download_imgs(urls, referer, name):
#     names = []
#     c = 1
#     for url in tqdm.tqdm(urls):
#         ext = get_filetype(url)
#         req = requests.get(url, headers={"Referer": referer})
#         assert req.status_code == 200
#         with open(f"{name}-{c}.{ext}", "wb") as file:
#             file.write(req.content)
#         names.append(f"{name}-{c}.{ext}")
#         c += 1
#     return names


# def download_imgs_of(urls, referer, name):
#     c = 1
#     for url in tqdm.tqdm(urls):
#         ext = get_filetype(url)
#         req = requests.get(url, headers={"Referer": referer})
#         assert req.status_code == 200
#         if ext != "gif":
#             arr = np.asarray(bytearray(req.content), dtype=np.uint8)
#             img = cv2.imdecode(arr, 1)
#         else:
#             with open("temp.gif", "wb") as f:
#                 f.write(req.content)
#             img = np.array(imageio.imread("temp.gif"))[:, :, :-1]
#             os.remove("temp.gif")
#         if c == 1:
#             curr = img
#         else:
#             if img.shape[1] > curr.shape[1]:
#                 img = img[:, : curr.shape[1] - img.shape[1], :]
#             elif img.shape[1] < curr.shape[1]:
#                 curr = curr[:, : img.shape[1] - curr.shape[1], :]
#             curr = cv2.vconcat([curr, img])
#         c += 1
#     cv2.imwrite(name + ".png", curr)
#     return name
