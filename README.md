# OSM (Personal) Info and Tools

Scripts in this repo: `osm_converter.py`, `pbf2osm.py`.

## Basic Info

- **Review:**
  - [OSMCha](https://osmcha.org) - Changeset history review
  - [Achavi](https://overpass-api.de/achavi) - Changeset history review.
    [Docs](https://wiki.openstreetmap.org/wiki/Achavi)
  - [Notes Review](https://notesreview.org) - Map notes review
- **Mapping:**
  - [taginfo](https://taginfo.openstreetmap.org) - Tag usage statistics
  - [Overpass Turbo](https://overpass-turbo.eu) - Query and download OSM data (see usage below)
  - [Level0](https://level0.osmz.ru) - Bulk edits editor (simpler than JOSM for text-based editing)
  - [JOSM](https://wiki.openstreetmap.org/wiki/JOSM) - Java-based desktop editor
- **File Formats:** 
  - [OsmChange](https://wiki.openstreetmap.org/wiki/OsmChange) - Change/diff format
  - [JOSM file format](https://wiki.openstreetmap.org/wiki/JOSM_file_format) - JOSM-specific OSM XML
  - [OSM JSON](https://wiki.openstreetmap.org/wiki/OSM_JSON) - JSON representation of OSM data
  - [GeoJSON](https://wiki.openstreetmap.org/wiki/GeoJSON) - Standard geospatial JSON format

## Overpass Turbo

Overpass Turbo allows downloading a subset of OSM objects for a specific area using a query language.
Examples:

All elements in the displayed map bounding box:
```
nwr({{bbox}});
out geom;
```
- `n` = nodes, `w` = ways, `r` = relations

Specific bounding box (south, west, north, east):
```
nwr(29.45,34.20,33.35,35.95);
out geom;
```

Get a specific element by ID:
```
node(13111799269);
out geom;
```

Search by tag with pattern matching (returns JOSM-compatible OSM XML with metadata):
```
node["name"~"something"];
way["name"~"something"];
out meta;
```

## OSM Converter

`osm_converter.py` is a Python converter for transforming between multiple OSM data formats. It is a single script file using only the Python standard library.

### Supported Formats

- **OSM XML** (`.osm`) - Standard OSM XML format (bidirectional)
- **OSM JSON** (`.json`) - JSON representation of OSM data
- **GeoJSON** (`.geojson`) - Standard GeoJSON format (bidirectional)
- **Level0L** (`.l0l`) - Level0 text format (bidirectional)
- **OsmChange** (`.osc`) - Change/diff format (one-way: from OSM/JSON to OsmChange)
- **CSV** (`.csv`) - line per object having a name. Tags are sorted and placed in columns (one-way)

### Usage

Formats are automatically determined by file extensions. Simply specify input and output files:

```sh
# XML to JSON
osm_converter.py input.osm output.json

# JSON to GeoJSON
osm_converter.py input.json output.geojson

# GeoJSON to OSM XML
osm_converter.py input.geojson output.osm

# OSM to Level0L
osm_converter.py input.osm output.l0l

# JOSM file to OsmChange (for changesets)
osm_converter.py josm_edits.osm changes.osc
```

### Notes

- **OsmChange conversion**: Requires JOSM-compatible input with `action` attributes (modify/delete) or negative IDs (create). Elements must have `changeset` and `version` attributes (except for negative IDs).
- **GeoJSON conversion**:
  - Nodes → Points
  - Open ways → LineStrings
  - Closed ways → Polygons
  - Metadata stored with `@` prefix in properties (e.g., `@version`, `@changeset`)
- **CSV**: usable for small extracts. `name:*` is filtered to include only `ar`, `en`, `he`

## PBF Converter

Converts OSM PBF (compressed) files to OSM XML. **VERY SLOW**.
Uses the `protobuf` library directly (not using `osmuim`).

```sh
pbf2osm input.pbf output.osm
```
