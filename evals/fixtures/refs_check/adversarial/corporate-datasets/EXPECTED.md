# corporate authors, software/dataset DOIs (DataCite, not Crossref)
MUST NOT report: c1, c2, c3, c5.
Expected false negative: c4 (a Zenodo DOI with a wrong title): DataCite DOIs are only checked for existence
(doi.org handle), never for the title. Fix: query https://api.datacite.org/dois/<doi> when Crossref gives 404.
