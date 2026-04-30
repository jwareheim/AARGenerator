mod error;
mod extract;
mod schema;

use clap::{Parser, Subcommand};
use error::ParserError;
use std::fs::File;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::process;
use zip::ZipArchive;

const PARSER_VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Parser)]
#[command(name = "stellaris-parser", version = PARSER_VERSION)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    Extract {
        path: PathBuf,

        #[arg(long)]
        pretty: bool,

        #[arg(long)]
        validate: bool,
    },
}

fn run() -> Result<(), ParserError> {
    let cli = Cli::parse();

    match cli.command {
        Command::Extract { path, pretty, validate } => {
            if !path.exists() {
                return Err(ParserError::FileNotFound(path.display().to_string()));
            }

            let file = File::open(&path).map_err(|e| {
                ParserError::FileNotFound(format!("{}: {}", path.display(), e))
            })?;

            let mut archive = ZipArchive::new(file).map_err(|e| {
                ParserError::InvalidSav(format!("Not a ZIP archive: {}", e))
            })?;

            let meta_bytes = read_entry(&mut archive, "meta")?;
            let gamestate_bytes = read_entry(&mut archive, "gamestate")?;

            check_binary_format(&gamestate_bytes)?;

            let snapshot = extract::extract(&meta_bytes, &gamestate_bytes)?;

            if validate {
                return Ok(());
            }

            let json = if pretty {
                serde_json::to_string_pretty(&snapshot)
            } else {
                serde_json::to_string(&snapshot)
            }
            .map_err(|e| ParserError::ParseError(format!("JSON serialization failed: {}", e)))?;

            std::io::stdout()
                .write_all(json.as_bytes())
                .map_err(|e| ParserError::ParseError(format!("Write failed: {}", e)))?;

            Ok(())
        }
    }
}

fn read_entry(archive: &mut ZipArchive<File>, name: &str) -> Result<Vec<u8>, ParserError> {
    let mut entry = archive.by_name(name).map_err(|_| {
        ParserError::InvalidSav(format!("Missing '{}' entry in .sav file", name))
    })?;
    let mut buf = Vec::new();
    entry
        .read_to_end(&mut buf)
        .map_err(|e| ParserError::ParseError(format!("Failed to read '{}': {}", name, e)))?;
    Ok(buf)
}

fn check_binary_format(bytes: &[u8]) -> Result<(), ParserError> {
    for &b in bytes.iter().take(256) {
        if b < 0x20 && b != b'\n' && b != b'\r' && b != b'\t' {
            return Err(ParserError::BinaryFormat);
        }
    }
    Ok(())
}

fn main() {
    match run() {
        Ok(()) => process::exit(0),
        Err(e) => {
            eprintln!("Error: {}", e);
            process::exit(e.exit_code());
        }
    }
}
