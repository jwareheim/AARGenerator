use crate::error::ParserError;
use crate::schema::Snapshot;

pub fn extract(
    _meta_bytes: &[u8],
    _gamestate_bytes: &[u8],
) -> Result<Snapshot, ParserError> {
    // Stub: return empty snapshot. Phases 2-6 fill this in.
    Ok(Snapshot::default())
}
