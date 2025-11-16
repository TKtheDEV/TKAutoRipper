# app/core/integration/omdbapi/helper.py
from pathlib import Path

def write_jellyfin_nfo(self, target_dir: Path) -> None:
    meta = self.metadata or {}
    title = str(meta.get("Title") or "").strip()
    year  = str(meta.get("Year") or "").strip()
    typ   = (meta.get("Type") or "").lower()
    imdb  = self.imdb_id or str(meta.get("imdbID") or "").strip()
    if not title:
        return
    if typ == "series":
        series_root = target_dir
        if series_root.name.lower().startswith("season "):
            series_root = series_root.parent
        root = ET.Element("tvshow")
        ET.SubElement(root, "title").text = title
        if year:
            ET.SubElement(root, "year").text = year
        if imdb:
            uid = ET.SubElement(root, "uniqueid")
            uid.set("type", "imdb")
            uid.set("default", "true")
            uid.text = imdb
        _write_xml(series_root / "tvshow.nfo", root)
    else:
        root = ET.Element("movie")
        ET.SubElement(root, "title").text = title
        if year:
            ET.SubElement(root, "year").text = year
        if imdb:
            uid = ET.SubElement(root, "uniqueid")
            uid.set("type", "imdb")
            uid.set("default", "true")
            uid.text = imdb
        _write_xml(target_dir / "movie.nfo", root)

    def write_jellyfin_nfo(self, target_dir: Path) -> None:
        meta = self.metadata or {}
        title = str(meta.get("Title") or "").strip()
        year  = str(meta.get("Year") or "").strip()
        typ   = (meta.get("Type") or "").lower()
        imdb  = self.imdb_id or str(meta.get("imdbID") or "").strip()
        if not title:
            return

        if typ == "series":
            series_root = target_dir
            if series_root.name.lower().startswith("season "):
                series_root = series_root.parent
            root = ET.Element("tvshow")
            ET.SubElement(root, "title").text = title
            if year:
                ET.SubElement(root, "year").text = year
            if imdb:
                uid = ET.SubElement(root, "uniqueid")
                uid.set("type", "imdb")
                uid.set("default", "true")
                uid.text = imdb
            _write_xml(series_root / "tvshow.nfo", root)
        else:
            root = ET.Element("movie")
            ET.SubElement(root, "title").text = title
            if year:
                ET.SubElement(root, "year").text = year
            if imdb:
                uid = ET.SubElement(root, "uniqueid")
                uid.set("type", "imdb")
                uid.set("default", "true")
                uid.text = imdb
            _write_xml(target_dir / "movie.nfo", root)
