import intake
import param

from ..util import get_dataframe_schema
from .base import Source, cached


class IntakeSource(Source):
    """
    An IntakeSource loads data from an Intake catalog.
    """

    catalog = param.Dict(doc="An inlined Catalog specification.")

    dask = param.Boolean(default=False, doc="""
        Whether to return a dask DataFrame.""")

    uri = param.String(doc="URI of the catalog file.")

    source_type = 'intake'

    def __init__(self, **params):
        super().__init__(**params)
        if self.uri and self.specification:
            raise ValueError("Either specify a Catalog uri or an "
                             "inlined catalog specification, not both.")
        elif self.uri:
            self.cat = intake.open_catalog(self.uri)
        elif self.catalog:
            context = {'root': self.root}
            result = intake.catalog.local.CatalogParser(self.catalog, context=context)
            if result.errors:
                raise intake.catalog.exceptions.ValidationError(
                    "Catalog '{}' has validation errors:\n\n{}"
                    "".format(self.path, "\n".join(result.errors)), result.errors)
            cfg = result.data
            del cfg['plugin_sources']
            entries = {entry.name: entry for entry in cfg.pop('data_sources')}
            self.cat = intake.catalog.Catalog(entries, **cfg)

    def _read(self, table, dask=True):
        if self.dask or dask:
            try:
                return self.cat[table].to_dask()
            except Exception:
                if self.dask:
                    self.param.warning(f"Could not load {table} table with dask.")
                pass
        return self.cat[table].read()

    def get_schema(self, table=None):
        schemas = {}
        for entry in list(self.cat):
            if table is not None and entry != table:
                continue
            data = self.get(entry, dask=True)
            schemas[entry] = get_dataframe_schema(data)['items']['properties']
        return schemas if table is None else schemas[table]

    @cached()
    def get(self, table, **query):
        dask = query.pop('dask', self.dask)
        df = self._read(table)
        df = self._filter_dataframe(df, **query)
        return df if dask or not hasattr(df, 'compute') else df.compute()
