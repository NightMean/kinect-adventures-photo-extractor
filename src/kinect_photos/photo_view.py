"""Sortable photo rows whose checkbox identities survive changes in order."""

from enum import IntEnum

from .catalog import PhotoEntry, PhotoSelection


class PhotoColumn(IntEnum):
    NAME = 0
    DATE = 1


class PhotoView:
    def __init__(self, photos: tuple[PhotoEntry, ...], checked: set[int] | None = None):
        self.photos = photos
        self.rows = list(range(len(photos)))
        self.selection = PhotoSelection(len(photos))
        if checked is not None:
            self.selection.checked = set(checked)
        self.column: PhotoColumn | None = None
        self.ascending = True

    @property
    def checked_indices(self) -> set[int]:
        return {self.rows[row] for row in self.selection.checked}

    def sort(self, column: PhotoColumn) -> None:
        checked = self.checked_indices
        anchor = self.rows[self.selection.anchor] if self.selection.anchor is not None else None
        self.ascending = not self.ascending if column == self.column else True
        self.column = column

        def name(index):
            entry = self.photos[index]
            return entry.source.path.name.casefold(), entry.number, entry.source.relative.casefold(), index

        if column == PhotoColumn.NAME:
            self.rows.sort(key=name, reverse=not self.ascending)
        else:
            dated = [index for index in self.rows if self.photos[index].date is not None]
            # Sort the displayed wall-clock dates: filename dates have no known timezone.
            dated.sort(key=lambda i: (self.photos[i].date.replace(tzinfo=None), name(i)),
                       reverse=not self.ascending)
            unknown = sorted((i for i in self.rows if self.photos[i].date is None), key=name)
            self.rows = dated + unknown
        self.selection.checked = {row for row, index in enumerate(self.rows) if index in checked}
        self.selection.anchor = self.rows.index(anchor) if anchor is not None else None
