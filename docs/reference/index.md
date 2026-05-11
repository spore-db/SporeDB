# API Reference

Auto-generated documentation for the SporeDB Python API.

## Core

- [SporeDB](sporedb.md#sporedb.SporeDB) -- primary entry point for all operations
- [Batch](sporedb.md#sporedb.Batch) -- fermentation batch record
- [ImportResult](sporedb.md#sporedb.ImportResult) -- result of a data import operation

## Phase Detection

- [DetectionConfig](sporedb.md#sporedb.DetectionConfig) -- phase detection parameters
- [PhaseAnnotation](sporedb.md#sporedb.PhaseAnnotation) -- detected phase boundary
- [PhaseType](sporedb.md#sporedb.PhaseType) -- phase type enumeration

## Models

- [BatchMetadata](sporedb.md#sporedb.BatchMetadata) -- batch metadata fields
- [BatchLifecycle](sporedb.md#sporedb.BatchLifecycle) -- batch lifecycle state
- [BatchMetrics](sporedb.md#sporedb.BatchMetrics) -- computed batch metrics
- [TelemetryRecord](sporedb.md#sporedb.TelemetryRecord) -- single telemetry data point
- [AssayMeasurement](sporedb.md#sporedb.AssayMeasurement) -- offline assay measurement
- [UncertainValue](sporedb.md#sporedb.UncertainValue) -- value with uncertainty bounds

## Storage

- [StorageEngine](sporedb.md#sporedb.StorageEngine) -- DuckDB + Parquet storage backend
- [BatchStore](sporedb.md#sporedb.BatchStore) -- batch CRUD operations
- [TimeSeriesStore](sporedb.md#sporedb.TimeSeriesStore) -- time-series data store
- [LineageStore](sporedb.md#sporedb.LineageStore) -- data lineage tracking
