use thiserror::Error;

#[derive(Error, Debug)]
pub enum ParserError {
    #[error("File not found: {0}")]
    FileNotFound(String),

    #[error("Not a valid .sav file: {0}")]
    InvalidSav(String),

    #[error("Parse error: {0}")]
    ParseError(String),

    #[error("Extraction error: {0}")]
    ExtractionError(String),

    #[error("Binary-encoded save format is not supported")]
    BinaryFormat,
}

impl ParserError {
    pub fn exit_code(&self) -> i32 {
        match self {
            ParserError::FileNotFound(_) => 1,
            ParserError::InvalidSav(_) => 2,
            ParserError::ParseError(_) => 3,
            ParserError::ExtractionError(_) => 4,
            ParserError::BinaryFormat => 5,
        }
    }
}
