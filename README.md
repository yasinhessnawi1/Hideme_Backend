# Hideme_Backend
[![Build Status](https://img.shields.io/badge/Status-production-green)]()
[![Test Coverage](https://img.shields.io/badge/Coverage-87%25-brightgreen)]()
[![Python Version](https://img.shields.io/badge/py-3.12%2B-blue)]()

A comprehensive backend service for detecting and redacting sensitive information in documents with a focus on Norwegian
language support, GDPR compliance, and high performance.

## Project Overview

Hideme_Backend is a FastAPI-based service designed to detect, extract, and redact sensitive information from documents,
particularly PDFs. It employs multiple detection engines including:

- **Presidio**: Microsoft's PII detection library
- **Gemini**: Google's generative AI for entity detection
- **GLiNER**: A specialized NER model for sensitive data detection
- **HIDEME**: A custom-trained model for Norwegian-specific sensitive data

The system is built with security, performance, and GDPR compliance as core principles, featuring rate limiting,
caching, memory optimization, and secure error handling. It supports both individual file processing and batch
operations, making it suitable for enterprise-level document processing needs.

## Key Features

- Multiple detection engines with hybrid detection capabilities
- PDF processing (extraction, redaction, searching)
- Batch processing for multiple files
- Norwegian language support with specialized entity types
- GDPR-compliant data handling with secure deletion
- Rate limiting and caching for performance optimization
- Memory management for handling large documents
- Comprehensive error handling with security focus
- Health and status monitoring endpoints

## Key Algorithms

### Entity Detection

#### 1. Text Extraction & Mapping Algorithm

The system extracts text from documents while preserving positional information:

```
1. Extract text with positional data
2. For each page in document:
   a. Get words with their bounding boxes
   b. Create a mapping between character positions and visual positions
   c. Store in a structured format for entity detection
```

#### 2. Text Segmentation Algorithm (GLiNER AND HIDEME)

GLiNER processes text in segments to handle token limits:

```
1. Split text into paragraphs
2. Group paragraphs into batches of appropriate size
3. For each text group:
   a. Process with GLiNER model
   b. Map detected entities back to original text positions
   c. Merge and deduplicate entities
```

#### 3. Redaction Mapping Algorithm

```
1. For each detected entity:
   a. Find all occurrences in the text
   b. Map text positions to document positions (bounding boxes)
   c. Create redaction boxes covering the sensitive content
```

### Hybrid Detection Algorithm

```
1. Process document with multiple detection engines in parallel
2. For each engine:
   a. Extract entities with confidence scores
   b. Track processing time and success/failure
3. Combine results from all engines
4. Prepare unified redaction mapping
```

## Setup Instructions

### Prerequisites

- Python 3.10+
- Redis (optional, for distributed caching and rate limiting)
- Docker and Docker Compose (for containerized deployment)

### Environment Variables

Create a `.env` file in the project root with the following variables:

```
# API Configuration
API_VERSION=1.0.0
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=False

# Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Redis (Optional)
REDIS_URL=redis://redis:6379/0

# Rate Limiting (Optional)
RATE_LIMIT_RPM=60
ADMIN_RATE_LIMIT_RPM=120
ANON_RATE_LIMIT_RPM=30
RATE_LIMIT_BURST=30

```

### Local Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yasinhessnawi1/Hideme_Backend.git
   cd Hideme_Backend
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Download required NLP models:
   ```bash
   python -m spacy download nb_core_news_lg
   ```

5. Run the application:
   ```bash
   python backend/main.py
   ```

The API will be available at `http://localhost:8000`.

### Docker Setup

1. Build and start the containers:
   ```bash
   docker-compose up -d
   ```

2. The API will be available at `http://localhost:8000`.

3. Check the logs:
   ```bash
   docker-compose logs -f
   ```

4. Stop the containers:
   ```bash
   docker-compose down
   ```

## Running Tests & Coverage

We use **pytest** along with **pytest-cov** to validate functionality and measure test coverage for the `backend.app`
package.

1. **Install testing dependencies**:
   ```bash
   pip install pytest pytest-cov
   ```

2. **Run tests and generate an HTML coverage report**:
   ```bash
   pytest --cov=backend.app --cov-report=html
   start htmlcov/index.html  # On macOS/Linux: open htmlcov/index.html
   ```

The generated report (as of **2025-05-02**) shows an overall test coverage of **87%**:

| File                                                      | statements | missing | excluded | coverage |
|-----------------------------------------------------------|-----------:|--------:|---------:|---------:|
| backend/app/**init**.py                                   |          3 |       0 |        0 |     100% |
| backend/app/api/**init**.py                               |          0 |       0 |        0 |     100% |
| backend/app/api/main.py                                   |        166 |      29 |        0 |      83% |
| backend/app/api/routes/**init**.py                        |          7 |       0 |        0 |     100% |
| backend/app/api/routes/ai\_routes.py                      |         31 |       5 |        0 |      84% |
| backend/app/api/routes/batch\_routes.py                   |        128 |      13 |        0 |      90% |
| backend/app/api/routes/machine\_learning.py               |         82 |       8 |        0 |      90% |
| backend/app/api/routes/metadata\_routes.py                |        126 |       3 |        0 |      98% |
| backend/app/api/routes/pdf\_routes.py                     |         36 |       0 |        0 |     100% |
| backend/app/api/routes/status\_routes.py                  |        112 |      23 |        0 |      79% |
| backend/app/configs/**init**.py                           |          0 |       0 |        0 |     100% |
| backend/app/configs/config\_singleton.py                  |         31 |       4 |        0 |      87% |
| backend/app/configs/gdpr\_config.py                       |         10 |       0 |        0 |     100% |
| backend/app/configs/gemini\_config.py                     |          8 |       0 |        0 |     100% |
| backend/app/configs/gliner\_config.py                     |          7 |       0 |        0 |     100% |
| backend/app/configs/hideme\_config.py                     |          7 |       0 |        0 |     100% |
| backend/app/configs/presidio\_config.py                   |          4 |       0 |        0 |     100% |
| backend/app/document\_processing/**init**.py              |          0 |       0 |        0 |     100% |
| backend/app/document\_processing/detection\_updater.py    |        125 |      27 |        0 |      78% |
| backend/app/document\_processing/pdf\_extractor.py        |        170 |      28 |        0 |      84% |
| backend/app/document\_processing/pdf\_redactor.py         |        192 |      33 |        0 |      83% |
| backend/app/document\_processing/pdf\_searcher.py         |        227 |      35 |        0 |      85% |
| backend/app/domain/**init**.py                            |          2 |       0 |        0 |     100% |
| backend/app/domain/interfaces.py                          |         23 |       6 |        0 |      74% |
| backend/app/entity\_detection/**init**.py                 |          8 |       0 |        0 |     100% |
| backend/app/entity\_detection/base.py                     |        203 |      21 |        0 |      90% |
| backend/app/entity\_detection/engines.py                  |          7 |       0 |        0 |     100% |
| backend/app/entity\_detection/gemini.py                   |        161 |      16 |        0 |      90% |
| backend/app/entity\_detection/gliner.py                   |         14 |       1 |        0 |      93% |
| backend/app/entity\_detection/glinerbase.py               |        437 |     254 |        0 |      42% |
| backend/app/entity\_detection/hideme.py                   |         14 |       1 |        0 |      93% |
| backend/app/entity\_detection/hybrid.py                   |        230 |      54 |        0 |      77% |
| backend/app/entity\_detection/presidio.py                 |        164 |      49 |        0 |      70% |
| backend/app/services/**init**.py                          |          4 |       0 |        0 |     100% |
| backend/app/services/ai\_detect\_service.py               |         54 |       5 |        0 |      91% |
| backend/app/services/base\_detect\_service.py             |        135 |       5 |        0 |      96% |
| backend/app/services/batch\_detect\_service.py            |        185 |      17 |        0 |      91% |
| backend/app/services/batch\_redact\_service.py            |        187 |       8 |        0 |      96% |
| backend/app/services/batch\_search\_service.py            |        150 |      24 |        0 |      84% |
| backend/app/services/document\_extract\_service.py        |         56 |       1 |        0 |      98% |
| backend/app/services/document\_redact\_service.py         |         65 |       3 |        0 |      95% |
| backend/app/services/initialization\_service.py           |        425 |      46 |        0 |      89% |
| backend/app/services/machine\_learning\_service.py        |         61 |       4 |        0 |      93% |
| backend/app/utils/**init**.py                             |          2 |       0 |        0 |     100% |
| backend/app/utils/constant/**init**.py                    |          0 |       0 |        0 |     100% |
| backend/app/utils/constant/constant.py                    |         36 |       0 |        0 |     100% |
| backend/app/utils/helpers/**init**.py                     |          5 |       0 |        0 |     100% |
| backend/app/utils/helpers/gemini\_helper.py               |        124 |      10 |        0 |      92% |
| backend/app/utils/helpers/gemini\_usage\_manager.py       |         73 |       7 |        0 |      90% |
| backend/app/utils/helpers/gliner\_helper.py               |         78 |       0 |        0 |     100% |
| backend/app/utils/helpers/json\_helper.py                 |        127 |       7 |        0 |      94% |
| backend/app/utils/helpers/ml\_models\_helper.py           |         25 |       0 |        0 |     100% |
| backend/app/utils/helpers/text\_utils.py                  |        105 |       0 |        0 |     100% |
| backend/app/utils/logging/**init**.py                     |          0 |       0 |        0 |     100% |
| backend/app/utils/logging/logger.py                       |         32 |       0 |        0 |     100% |
| backend/app/utils/logging/secure\_logging.py              |         15 |       0 |        0 |     100% |
| backend/app/utils/parallel/**init**.py                    |          0 |       0 |        0 |     100% |
| backend/app/utils/parallel/core.py                        |        205 |       9 |        0 |      96% |
| backend/app/utils/security/**init**.py                    |          0 |       0 |        0 |     100% |
| backend/app/utils/security/caching\_middleware.py         |        239 |      19 |        0 |      92% |
| backend/app/utils/security/processing\_records.py         |        109 |      13 |        0 |      88% |
| backend/app/utils/security/rate\_limiting.py              |        101 |       3 |        0 |      97% |
| backend/app/utils/security/retention\_management.py       |        128 |       6 |        0 |      95% |
| backend/app/utils/security/session\_encryption.py         |        231 |      26 |        0 |      89% |
| backend/app/utils/system\_utils/**init**.py               |          0 |       0 |        0 |     100% |
| backend/app/utils/system\_utils/error\_handling.py        |        281 |      25 |        0 |      91% |
| backend/app/utils/system\_utils/memory\_management.py     |        347 |      50 |        0 |      86% |
| backend/app/utils/system\_utils/secure\_file\_utils.py    |        112 |      14 |        0 |      88% |
| backend/app/utils/system\_utils/synchronization\_utils.py |        311 |      20 |        0 |      94% |
| backend/app/utils/validation/**init**.py                  |          0 |       0 |        0 |     100% |
| backend/app/utils/validation/data\_minimization.py        |        129 |       6 |        0 |      95% |
| backend/app/utils/validation/file\_validation.py          |        143 |       5 |        0 |      97% |
| backend/app/utils/validation/sanitize\_utils.py           |         99 |       1 |        0 |      99% |
| **Total**                                                 |      7,114 |     944 |        0 |  **87%** |

## Project Structure

The project follows a modular architecture with the following structure:

```
backend/
├── app/
│   ├── api/                              # API routes and endpoints
│   │   ├── __init__.py
│   │   ├── main.py                       # API initialization
│   │   └── routes/                       # Route definitions
│   │       ├── __init__.py
│   │       ├── ai_routes.py
│   │       ├── batch_routes.py
│   │       ├── machine_learning.py
│   │       ├── metadata_routes.py
│   │       ├── pdf_routes.py
│   │       └── status_routes.py
│   ├── configs/                          # Configuration files
│   │   ├── __init__.py
│   │   ├── analyzer-config.yml
│   │   ├── config_singleton.py
│   │   ├── gdpr_config.py
│   │   ├── gemini_config.py
│   │   ├── gliner_config.py
│   │   ├── hideme_config.py
│   │   ├── nlp-config.yml
│   │   ├── presidio_config.py
│   │   └── recognizers-config.yml
│   ├── domain/                           # Domain interfaces and models
│   │   ├── __init__.py
│   │   └── interfaces.py
│   ├── document_processing/              # PDF processing utilities
│   │   ├── __init__.py
│   │   ├── detection_updater.py
│   │   ├── pdf_extractor.py
│   │   ├── pdf_redactor.py
│   │   └── pdf_searcher.py
│   ├── entity_detection/                 # Entity detection engines
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── engines.py
│   │   ├── gemini.py
│   │   ├── gliner.py
│   │   ├── glinerbase.py
│   │   ├── hideme.py
│   │   ├── hybrid.py
│   │   └── presidio.py
│   ├── services/                         # Business logic and service layers
│   │   ├── __init__.py
│   │   ├── ai_detect_service.py
│   │   ├── base_detect_service.py
│   │   ├── batch_detect_service.py
│   │   ├── batch_redact_service.py
│   │   ├── batch_search_service.py
│   │   ├── document_extract_service.py
│   │   ├── document_redact_service.py
│   │   ├── initialization_service.py
│   │   └── machine_learning_service.py
│   └── utils/                            # Utility modules
│       ├── __init__.py
│       ├── constant/                     # Constants
│       │   ├── __init__.py
│       │   └── constant.py
│       ├── helpers/                      # Helper functions
│       │   ├── __init__.py
│       │   ├── gemini_helper.py
│       │   ├── gemini_usage_manager.py
│       │   ├── gliner_helper.py
│       │   ├── json_helper.py
│       │   ├── ml_models_helper.py
│       │   └── text_utils.py
│       ├── logging/                      # Logging utilities
│       │   ├── __init__.py
│       │   ├── logger.py
│       │   └── secure_logging.py
│       ├── parallel/                     # Parallel processing utilities
│       │   ├── __init__.py
│       │   └── core.py
│       ├── security/                     # Security features
│       │   ├── __init__.py
│       │   ├── caching_middleware.py
│       │   ├── processing_records.py
│       │   ├── rate_limiting.py
│       │   ├── retention_management.py
│       │   └── session_encryption.py
│       ├── system_utils/                 # System utilities
│       │   ├── __init__.py
│       │   ├── error_handling.py
│       │   ├── memory_management.py
│       │   ├── secure_file_utils.py
│       │   └── synchronization_utils.py
│       └── validation/                   # Input validation utilities
│           ├── __init__.py
│           ├── data_minimization.py
│           ├── file_validation.py
│           └── sanitize_utils.py
├── tests/                                # Test cases
├── docker-compose.yml                    # Docker Compose configuration
├── Dockerfile                            # Docker build instructions
├── main.py                               # Application entry point
└── requirements.txt                      # Python dependencies

```

## Configuration Files

### presidio_config.py

Configures Microsoft Presidio for entity detection with Norwegian language support. Defines available entity types for
detection, including Norwegian-specific entities like:

- `NO_FODSELSNUMMER_P` (Norwegian national identity number)
- `NO_PHONE_NUMBER_P` (Norwegian phone numbers)
- `NO_ADDRESS_P` (Norwegian addresses)
- `NO_BANK_ACCOUNT_P` (Norwegian bank account numbers)
- `NO_COMPANY_NUMBER_P` (Norwegian organization numbers)
- `NO_LICENSE_PLATE_P` (Norwegian license plates)

### nlp-config.yml

Configures the NLP engine (spaCy) for entity recognition:

```yaml
nlp_engine_name: spacy
models:
  - lang_code: nb               # Norwegian Bokmål
    model_name: nb_core_news_lg # Large Norwegian language model
```

Includes mappings from model-specific entity labels to standardized entity names and confidence score adjustments.

### hideme_config.py

Configures the custom HIDEME model for Norwegian-specific entity detection:

- Model name: `yasin9999/gliner_finetuned_v1`
- Local storage path for downloaded model
- Supported entity types (21 types including Norwegian-specific entities)

### gliner_config.py

Configures the GLiNER model for entity detection:

- Model name: `urchade/gliner_multi_pii-v1`
- Local storage path for downloaded model
- Supported entity types (33 types of personal information)

### gemini_config.py

Configures Google's Gemini AI for entity detection:

- Prompt templates for entity detection
- System instructions for Norwegian language processing
- Available entity types with detailed descriptions

### gdpr_config.py

GDPR-related configuration settings:

- Retention periods for temporary and redacted files
- Data minimization rules
- Anonymization configuration
- Processing record settings
- Data subject rights support
- GDPR documentation

## API Routes

### AI Detection

#### POST /ai/detect

Detects sensitive information in a document using AI-based detection.

**Parameters:**

- `file`: The document to analyze (multipart/form-data)
- `requested_entities`: Optional comma-separated list of entities to detect
- `remove_words`: Optional comma-separated list of words to remove
- `threshold`: Optional confidence threshold (0.0-1.0)

**Response:**

``` json
{
  "redaction_mapping": {
    "pages": [
      {
        "page": 1,
        "sensitive": [
          {
            "engine": "gemini",
            "entity_type": "PERSON-G",
            "start": 91,
            "end": 108,
            "score": 0.95,
            "bbox": {
              "x0": 283.909912109375,
              "y0": 789.9979858398438,
              "x1": 351.92486572265625,
              "y1": 795.3807983398438
            }
          },
          {
            "engine": "gemini",
            "entity_type": "EMAIL-G",
            "start": 130,
            "end": 150,
            "score": 0.97,
            "bbox": {
              "x0": 251.7693328857422,
              "y0": 809.43798828125,
              "x1": 354.3266296386719,
              "y1": 814.82080078125
            }
          }
        ]
      }
    ]
  },
  "entities_detected": {
    "total": 2,
    "by_type": {
      "PERSON-G": 1,
      "EMAIL-G": 1
    },
    "by_page": {
      "page_1": 2
    }
  },
  "processing_time": 0.89
}

```

### Presidio, Gliner and HideMe Detection

#### POST /ml/detect

Detects sensitive information in a document using Presidio detection.

**Parameters:**

- `file`: The document to analyze (multipart/form-data)
- `requested_entities`: Optional comma-separated list of entities to detect
- `remove_words`: Optional comma-separated list of words to remove
- `threshold`: Optional confidence threshold (0.0-1.0)

**Response:**

``` json
{
  "redaction_mapping": {
    "pages": [
      {
        "page": 1,
        "sensitive": [
          {
            "engine": "presidio",
            "entity_type": "ORGANIZATION_P",
            "start": 0,
            "end": 11,
            "score": 0.8,
            "bbox": {
              "x0": 70.800048828125,
              "y0": 789.9979858398438,
              "x1": 111.3972396850586,
              "y1": 795.3807983398438
            }
          }
          {
            /* Additional sensitive blocks */
          }
        ]
      },
      {
        /* Page 2 sensitive entities */
      }
    ]
  },
  "entities_detected": {
    "total": 26,
    "by_type": {
      "ORGANIZATION_P": 6,
      "PERSON_P": 7,
      "NO_PHONE_NUMBER_P": 4,
      "EMAIL_ADDRESS_P": 1,
      "NO_ADDRESS_P": 2,
      "DATE_TIME_P": 4,
      "LOCATION_P": 2
    },
    "by_page": {
      "page_1": 15,
      "page_2": 11
    }
  },
  "performance": {
    "file_read_time": 0.0,
    "extraction_time": 0.04659,
    "detection_time": 1.15947,
    "total_time": 1.21662,
    "words_count": 613,
    "pages_count": 2,
    "entity_density": 50.571,
    "sanitize_time": 0.000839
  },
  "file_info": {
    "filename": "Anspeksjonsrapport.pdf",
    "content_type": "application/pdf",
    "size": "0.07 MB"
  },
  "model_info": {
    "engine": "presidio"
  },
  "_debug": {
    "memory_usage": 0.38156,
    "peak_memory": 36.37794
  }
}
```

#### POST /ml/gl_detect

Detects sensitive information in a document using Gliner detection.

**Parameters:**

- `file`: The document to analyze (multipart/form-data)
- `requested_entities`: Optional comma-separated list of entities to detect
- `remove_words`: Optional comma-separated list of words to remove
- `threshold`: Optional confidence threshold (0.0-1.0)

**Response:** Same as `/ml/detect`

#### POST /ml/hm_detect

Detects sensitive information in a document using HideMe detection.

**Parameters:**

- `file`: The document to analyze (multipart/form-data)
- `requested_entities`: Optional comma-separated list of entities to detect
- `remove_words`: Optional comma-separated list of words to remove
- `threshold`: Optional confidence threshold (0.0-1.0)

**Response:** Same as `/ml/detect`

### PDF Processing

#### POST /pdf/redact

Applies redactions to a PDF file based on a provided redaction mapping.

**Parameters:**

- `file`: The PDF file to redact (multipart/form-data)
- `redaction_mapping`: JSON string defining areas to redact
- `remove_images`: Boolean flag to remove images (default: false)

**Response:**

- Redacted PDF file as a stream

#### POST /pdf/extract

Extracts text with positions from a PDF file.

**Parameters:**

- `file`: The PDF file to extract text from (multipart/form-data)

**Response:**

```json
{
  "pages": [
    {
      "page": 1,
      "words": [
        {
          "x0": 70.800048828125,
          "y0": 787.9979858398438,
          "x1": 111.3972396850586,
          "y1": 797.3807983398438
        },
        {
          "x0": 70.800048828125,
          "y0": 797.5979614257812,
          "x1": 91.99494171142578,
          "y1": 806.9807739257812
        }
      ]
    }
  ]
}
```

### Batch Processing

#### POST /batch/detect

Processes multiple files for entity detection in parallel by using one engine.

**Form-data parameters:**

- `files` (required): One or more files to process (multipart/form-data).
- `requested_entities` (optional): Comma-separated list of entity types to detect (e.g. `PERSON_P`).
- `detection_engine` (optional): Which engine to use; one of `presidio`, `gemini`, `gliner`, `hideme`).
- `max_parallel_files` (optional): Maximum number of concurrent file analyses (default: `4`).
- `remove_words` (optional): Comma-separated words to strip before analysis.
- `threshold` (optional): Confidence cutoff between `0.0` and `1.0`.

**Headers (choose one mode):**

1. **Session-authenticated mode**
    - `session-key`: your session token
    - `api-key-id`: your key identifier
    - *All inputs (files + requested_entities + remove_words) must be AES-GCM encrypted.*
    - *Response is AES-GCM encrypted & base64-URL encoded in* `"encrypted_data"`.

2. **Raw-API-key mode**
    - `raw-api-key`: 256-bit key (URL-safe base64)
    - *Input values (files + requested_entities + remove_words) may be encrypted or plaintext; if any decryption succeeds, the response will be encrypted.*
    - *Encrypted response in* `"encrypted_data"`; *otherwise plaintext JSON.*

3. **Public mode (no encryption)**
    - *No special headers required.*
    - *Inputs and response are handled as plaintext.*

**Response:**

``` json
{
  "batch_summary": {
    "batch_id": "23804f68-af4d-4fcf-99da-26776a307982",
    "total_files": 3,
    "successful": 3,
    "failed": 0,
    "total_time": 19.4925537109375,
    "workers": 4
  },
  "file_results": [
    {
      "file": "Anspeksjonsrapport.pdf",
      "status": "success",
      "results": {
        "redaction_mapping": {
          "pages": [
            {
              "page": 1,
              "sensitive": [
                {
                  "engine": "hideme",
                  "entity_type": "PERSON-H",
                  "start": 91,
                  "end": 108,
                  "score": 0.985205352306366,
                  "bbox": {
                    "x0": 283.909912109375,
                    "y0": 789.9979858398438,
                    "x1": 351.92486572265625,
                    "y1": 795.3807983398438
                  }
                },
                {
                  /* Additional sensitive entity objects */
                }
              ]
            },
            {
              "page": 2,
              "sensitive": [
                {
                  "engine": "hideme",
                  "entity_type": "DATE_TIME-H",
                  "start": 56,
                  "end": 66,
                  "score": 0.9432600736618042,
                  "bbox": {
                    "x0": 393.42767333984375,
                    "y0": 30.592365264892578,
                    "x1": 433.42529296875,
                    "y1": 35.439002990722656
                  }
                }
                {
                  /* More sensitive entities on page 2 */
                }
              ]
            }
          ]
        },
        "entities_detected": {
          "total": 15,
          "by_type": {
            "PERSON-H": 7,
            "NO_PHONE_NUMBER-H": 1,
            "EMAIL_ADDRESS-H": 1,
            "NO_ADDRESS-H": 2,
            "DATE_TIME-H": 4
          },
          "by_page": {
            "page_1": 11,
            "page_2": 4
          }
        },
        "performance": {
          "words_count": 613,
          "pages_count": 2,
          "entity_density": 53.833605220228385,
          "sanitize_time": 0.00112152099609375
        },
        "file_info": {
          "filename": "Anspeksjonsrapport.pdf",
          "content_type": "application/pdf",
          "size": "0.07 MB"
        },
        "model_info": {
          "engine": "HIDEME"
        }
      }
    },
    {
      /* Responses for Bekymringsmelding.pdf and BekymringsmeldingWithImage.pdf follow similar structure */
    }
  ],
  "_debug": {
    "memory_usage": 8.159359097921785,
    "peak_memory": 36.377941030219056,
    "operation_id": "23804f68-af4d-4fcf-99da-26776a307982"
  }
}
```

#### POST /batch/hybrid_detect

Processes multiple files using a hybrid detection approach (multiple engines).

**Form-data parameters:**

- `files` (required): One or more files to process (multipart/form-data).
- `requested_entities` (optional): Comma-separated list of entity types to detect (e.g. `PERSON_P`).
- `use_presidio` (optional): `true` to enable Presidio engine (default: `true`).
- `use_gemini` (optional): `true` to enable Gemini engine (default: `false`).
- `use_gliner` (optional): `true` to enable GLiNER engine (default: `false`).
- `use_hideme` (optional): `true` to enable HideMe engine (default: `false`).
- `max_parallel_files` (optional): Maximum number of concurrent file analyses (default: `4`).
- `remove_words` (optional): Comma-separated words to strip before analysis.
- `threshold` (optional): Confidence cutoff between `0.0` and `1.0`.

**Headers (choose one mode):**

1. **Session-authenticated mode**
    - `session-key`: your session token
    - `api-key-id`: your key identifier
    - *All inputs (files + requested_entities + remove_words) must be AES-GCM encrypted.*
    - *Response is AES-GCM encrypted & base64-URL encoded in* `"encrypted_data"`.

2. **Raw-API-key mode**
    - `raw-api-key`: 256-bit key (URL-safe base64)
    - *Inputs (files + requested_entities + remove_words) may be encrypted or plaintext; if any decryption succeeds, response is encrypted.*
    - *Encrypted response in* `"encrypted_data"`; *otherwise plaintext JSON.*

3. **Public mode (no encryption)**
    - *No special headers required.*
    - *Inputs and response are handled as plaintext.*

**Response:** Same as `/batch/detect`

#### POST /batch/search

Searches for specific terms in multiple PDF files in parallel.

**Form-data parameters:**

- `files` (required): One or more PDF files to search (multipart/form-data).
- `search_terms` (required): Space-separated string of terms to search for.
- `case_sensitive` (optional): `true` to perform a case-sensitive match (default: `false`).
- `ai_search` (optional): `true` to enable AI-powered search enhancements (default: `false`).
- `max_parallel_files` (optional): Maximum number of concurrent file analyses (default: `4`).

**Headers (choose one mode):**

1. **Session-authenticated mode**
    - `session-key`: your session token
    - `api-key-id`: your key identifier
    - *All inputs (files + search_terms) must be AES-GCM encrypted.*
    - *Response is AES-GCM encrypted & base64-URL encoded in* `"encrypted_data"`.

2. **Raw-API-key mode**
    - `raw-api-key`: 256-bit key (URL-safe base64)
    - *Inputs (files + search_terms) may be encrypted or plaintext; if any decryption succeeds, response is encrypted.*
    - *Encrypted response in* `"encrypted_data"`; *otherwise plaintext JSON.*

3. **Public mode (no encryption)**
    - *No special headers required.*
    - *Inputs and response are handled as plaintext.*

**Response:**

``` json
{
  "batch_summary": {
    "batch_id": "search-41834a51-6380-4033-b02e-47ecd2eec3ca",
    "total_files": 1,
    "successful": 1,
    "failed": 0,
    "total_matches": 4,
    "search_term": "Jeanett, Lofthagen",
    "query_time": 0.13
  },
  "file_results": [
    {
      "file": "Anspeksjonsrapport.pdf",
      "status": "success",
      "results": {
        "pages": [
          {
            "page": 1,
            "matches": [
              {
                "bbox": {
                  "x0": 283.909912109375,
                  "y0": 787.9979858398438,
                  "x1": 311.77276611328125,
                  "y1": 797.3807983398438
                }
              },
              {
                /* More matching bounding boxes */
              }
            ]
          },
          {
            "page": 2,
            "matches": []
          }
        ],
        "match_count": 4
      }
    }
  ],
  "_debug": {
    "memory_usage": 8.218977653715642,
    "peak_memory": 36.377941030219056,
    "operation_id": "search-41834a51-6380-4033-b02e-47ecd2eec3ca"
  }
}
```

#### POST /batch/find_words

Finds words in multiple PDF files within a specified region.

**Form-data parameters:**

- `files` (required): One or more PDF files to process (multipart/form-data).
- `bounding_box` (required): JSON string with numeric keys `"x0"`, `"y0"`, `"x1"`, and `"y1"` defining the search
  rectangle, e.g. `{"x0":0,"y0":0,"x1":100,"y1":50}`.

**Headers (choose one mode):**

1. **Session-authenticated mode**
    - `session-key`: your session token
    - `api-key-id`: your key identifier
    - *All inputs (files + bounding_box) must be AES-GCM encrypted.*
    - *Response is AES-GCM encrypted & base64-URL encoded in* `"encrypted_data"`.

2. **Raw-API-key mode**
    - `raw-api-key`: 256-bit key (URL-safe base64)
    - *Inputs (files + bounding_box) may be encrypted or plaintext; if any decryption succeeds, response is encrypted.*
    - *Encrypted response in* `"encrypted_data"`; *otherwise plaintext JSON.*

3. **Public mode (no encryption)**
    - *No special headers required.*
    - *Inputs and response are handled as plaintext.*

**Response:**

```json
{
  "batch_summary": {
    "batch_id": "batch_find_words_1744718497",
    "total_files": 1,
    "successful": 1,
    "failed": 0,
    "total_matches": 1,
    "search_term": "Bounding Box: {'x0': 70.800048828125, 'y0': 132.64877319335938, 'x1': 175.97254943847656, 'y1': 152.64877319335938}",
    "query_time": 0.02
  },
  "file_results": [
    {
      "file": "Anspeksjonsrapport.pdf",
      "status": "success",
      "results": {
        "pages": [
          {
            "page": 1,
            "matches": [
              {
                "bbox": {
                  "x0": 70.800048828125,
                  "y0": 132.64877319335938,
                  "x1": 175.97254943847656,
                  "y1": 152.64877319335938
                }
              }
            ]
          },
          {
            "page": 2,
            "matches": []
          }
        ],
        "match_count": 1
      }
    }
  ],
  "_debug": {
    "memory_usage": 1.2187178313633176,
    "peak_memory": 43.97698984089396,
    "operation_id": "batch_find_words_1744718497"
  }
}
```

#### POST /batch/redact

Applies redactions to one or more PDF documents and returns the results as a ZIP archive (encrypted if requested).

**Form-data parameters:**

- `files` (required): One or more PDF files to redact (multipart/form-data).
- `redaction_mappings` (required): JSON string (or AES-GCM encrypted blob) mapping sensitive fields to redacted values.
- `remove_images` (optional, default: `false`): Set to `true` to strip all images from the PDFs.
- `max_parallel_files` (optional): Maximum number of documents to process concurrently (default: server-configured).

**Headers (choose one mode):**

1. **Session-authenticated mode**
    - `session-key`: your session token
    - `api-key-id`: your key identifier
    - *Inputs (files + redaction_mappings) must be AES-GCM encrypted.*
    - *Response ZIP is AES-GCM encrypted & base64-URL encoded in* `"encrypted_data"`.

2. **Raw-API-key mode**
    - `raw-api-key`: 256-bit key (URL-safe base64)
    - *Inputs (files + redaction_mappings) may be encrypted or plaintext; if any decryption succeeds, response is encrypted.*
    - *Encrypted response in* `"encrypted_data"`; *otherwise streams raw ZIP.*

3. **Public mode (no encryption)**
    - *No special headers required.*
    - *Inputs and response are plaintext; response streams raw ZIP.*

**Response:**

- ZIP file containing redacted documents

### Status and Metadata

#### GET /status

Returns a simple API status with current timestamp and version info.

**Response:**

```json
{
  "status": "success",
  "timestamp": 1650123456.789,
  "api_version": "1.0.0"
}
```

#### GET /health

Performs a health check for the system with detailed metrics.

**Response:**

```json
{
  "status": "healthy",
  "timestamp": 1744738132.0504751,
  "services": {
    "api": "online",
    "document_processing": "online"
  },
  "process": {
    "cpu_percent": 0.0,
    "memory_percent": 0.5239663990860918,
    "threads_count": 8,
    "uptime": 1428.9885771274567
  },
  "memory": {
    "peak_usage": 36.377941030219056,
    "average_usage": 2.689894235046888,
    "checks_count": 285,
    "emergency_cleanups": 0,
    "last_check_time": 1744738131.3771946,
    "current_usage": 0.5148543927420526,
    "available_memory_mb": 319.4921875,
    "system_threshold_adjustments": 5,
    "batch_operations": 0,
    "batch_peak_memory": 0.0
  },
  "cache": {
    "cache_size": 2,
    "cached_endpoints": [
      "api_status",
      "d15a8ffc0be88dadeacbf9dbe856353966a3b69a9763aac3053c89e7707bbd09"
    ]
  },
  "debug": {
    "environment": "development",
    "python_version": "unknown",
    "host": "unknown"
  }
}
```

#### GET /metrics

Retrieves system and process performance metrics.

**Response:**

```json
{
  "timestamp": 1744738168.546603,
  "system": {
    "cpu_percent": 2.0,
    "memory_percent": 94.9,
    "memory_available": 402874368,
    "memory_total": 7866544128
  },
  "process": {
    "cpu_percent": 0.0,
    "memory_rss": 41918464,
    "memory_percent": 0.53287013099941,
    "threads_count": 7,
    "open_files": 4,
    "connections": 4
  },
  "memory_monitor": {
    "peak_usage": 36.377941030219056,
    "average_usage": 2.6380756230049944,
    "checks_count": 292,
    "emergency_cleanups": 0,
    "last_check_time": 1744738166.4866128,
    "current_usage": 0.5283922307389108,
    "available_memory_mb": 394.7265625,
    "system_threshold_adjustments": 5,
    "batch_operations": 0,
    "batch_peak_memory": 0.0
  },
  "cache": {
    "cache_size": 4,
    "cache_keys": 4
  }
}
```

#### GET /readiness

Performs a readiness check to determine if the service is ready to accept requests.

**Response:**

```json
{
  "ready": true,
  "services": {
    "presidio_ready": true,
    "gemini_ready": true,
    "gliner_ready": true,
    "hideme_ready": true
  },
  "memory": {
    "usage_percent": 0.5704115971368514,
    "status": "ok"
  }
}
```

#### GET help/engines

Gets the list of available entity detection engines.

**Response:**

```json
{
  "engines": [
    "PRESIDIO",
    "GEMINI",
    "GLINER",
    "HIDEME",
    "HYBRID"
  ]
}
```

#### GET help/entities

Gets the list of available entity types for detection.

**Response:**

```json
{
  "presidio_entities": [
    "NO_FODSELSNUMMER_P",
    "NO_PHONE_NUMBER_P",
    "EMAIL_ADDRESS_P",
    "..."
  ],
  "gemini_entities": [
    "PERSON-G",
    "ORGANIZATION-G",
    "LOCATION-G",
    "..."
  ],
  "gliner_entities": [
    "person",
    "location",
    "date",
    "..."
  ],
  "hideme_entities": [
    "AGE-H",
    "DATE_TIME-H",
    "EMAIL_ADDRESS-H",
    "..."
  ]
}
```

#### GET help/entity-examples

Get examples for different entity types with improved response time.

**Response:**

```json
{
  "examples": {
    "PERSON": [
      "John Doe",
      "Jane Smith",
      "Dr. Robert Johnson"
    ],
    "EMAIL_ADDRESS": [
      "john.doe@example.com",
      "contact@company.org"
    ],
    "PHONE_NUMBER": [
      "+1 (555) 123-4567",
      "555-987-6543"
    ],
    "CREDIT_CARD": [
      "4111 1111 1111 1111",
      "5500 0000 0000 0004"
    ],
    "ADDRESS": [
      "123 Main St, Anytown, CA 12345",
      "456 Park Avenue, Suite 789"
    ],
    "DATE": [
      "January 15, 2023",
      "05/10/1985"
    ],
    "LOCATION": [
      "New York City",
      "Paris, France",
      "Tokyo"
    ],
    "ORGANIZATION": [
      "Acme Corporation",
      "United Nations",
      "Stanford University"
    ]
  }
}
```

#### GET help/detectors-status

Get status information for all cached entity detectors.

**Response:**

``` json
{
  "presidio": {
    "initialized": true,
    "initialization_time": 1744736720.0978835,
    "initialization_time_readable": "2025-04-15 19:05:20",
    "last_used": 1744737095.839356,
    "last_used_readable": "2025-04-15 19:11:35",
    "idle_time": 74.92768812179565,
    "idle_time_readable": "74.93 seconds",
    "total_calls": 1,
    "total_entities_detected": 62,
    "total_processing_time": 1.1633844375610352,
    "average_processing_time": 1.1633844375610352
  },
  "gemini": {
    /* Initialization and usage details */
  },
  "gliner": {
    /* GLiNER model info and initialization details */
  },
  "hideme": {
    /* HIDEME model details with paths and processing stats */
  },
  "_meta": {
    "last_updated": "2025-04-15T19:12:50.761412",
    "cache_ttl": 60
  }
}
```

#### GET help/routes

Provide a comprehensive overview of all available API routes.

**Response:**

```json
{
  "entity_detection": [
    {
      "path": "/ml/detect",
      "method": "POST",
      "description": "Presidio entity detection",
      "engine": "Presidio"
    },
    {
      "path": "/ml/gl_detect",
      "method": "POST",
      "description": "GLiNER entity detection",
      "engine": "GLiNER"
    },
    {
      "path": "/ai/detect",
      "method": "POST",
      "description": "Gemini AI entity detection",
      "engine": "Gemini"
    },
    {
      "path": "/ml/hm_detect",
      "method": "POST",
      "description": "HIDEME entity detection",
      "engine": "HIDEME"
    }
  ],
  "batch_processing": [
    {
      "path": "/batch/detect",
      "method": "POST",
      "description": "Batch sensitive data detection using one detection engine"
    },
    {
      "path": "/batch/hybrid_detect",
      "method": "POST",
      "description": "Hybrid batch detection across multiple engines"
    },
    {
      "path": "/batch/search",
      "method": "POST",
      "description": "Batch text search in multiple files"
    },
    {
      "path": "/batch/find_words",
      "method": "POST",
      "description": "Batch find words in PDF files based on bounding box"
    },
    {
      "path": "/batch/redact",
      "method": "POST",
      "description": "Batch document redaction returning a ZIP file"
    }
  ],
  "pdf_processing": [
    {
      "path": "/pdf/redact",
      "method": "POST",
      "description": "PDF document redaction"
    },
    {
      "path": "/pdf/extract",
      "method": "POST",
      "description": "PDF text extraction"
    }
  ],
  "metadata": [
    {
      "path": "/help/engines",
      "method": "GET",
      "description": "List available detection engines"
    },
    {
      "path": "/help/entities",
      "method": "GET",
      "description": "List available entity types"
    },
    {
      "path": "/help/entity-examples",
      "method": "GET",
      "description": "Get examples of different entity types"
    },
    {
      "path": "/help/detectors-status",
      "method": "GET",
      "description": "Get status of detection engines"
    },
    {
      "path": "/help/routes",
      "method": "GET",
      "description": "Comprehensive overview of API routes"
    }
  ],
  "system": [
    {
      "path": "/status",
      "method": "GET",
      "description": "Basic API status"
    },
    {
      "path": "/health",
      "method": "GET",
      "description": "Detailed health check"
    },
    {
      "path": "/metrics",
      "method": "GET",
      "description": "Performance metrics"
    },
    {
      "path": "/readiness",
      "method": "GET",
      "description": "Service readiness check"
    }
  ]
}
```

## Services

### Entity Detection Engines

#### Base Detection Engine:

- Abstract base class that defines the interface for all entity detection engines.

#### Presidio Engine:

- Uses Microsoft's Presidio Analyzer for entity detection with Norwegian language support.

#### Gemini Engine:

- Uses Google's Gemini AI for entity detection with specialized prompts for Norwegian text.

#### GLiNER Engine:

- Uses the GLiNER model for entity detection with support for multiple languages.

#### HIDEME Engine:

- Custom-trained model specifically for Norwegian sensitive data detection.

#### Hybrid Engine:

- Combines results from multiple detection engines to improve accuracy.

### Document Processing

#### Detection Result Updater:

- Responsible for updating a detection result by processing sensitive entities extracted from PDF pages.
- It removes specified phrases from entity texts and, if necessary, splits entities into multiple entries.

#### Document Extractor:

- Extracts text with positional information from documents.

#### Document Redactor:

- Applies redactions to documents based on detection results.

#### PDF Searcher:

- Responsible for finding specific search terms within text extracted from PDFs

### Services

#### AI Detect Service:

- Handles AI-based sensitive data detection for individual files.

#### Batch Detect Service:

- Manages batch processing of multiple files for entity detection.

#### Batch Redact Service:

- Applies redactions to multiple documents in parallel.

#### Batch Search Service:

- Searches for specific terms or bounding boxes in multiple documents.

#### Document Extract Service:

- Extracts text and positional information from documents.

#### Document Redact Service:

- Applies redactions to documents based on detection results.

#### Initialization Service:

- Manages initialization of detection engines and other services.

#### Machine Learning Service:

- Provides machine learning capabilities for entity detection.

## Security Considerations

### Rate Limiting

The system implements rate limiting to prevent abuse:

- Default: 60 requests per minute
- Admin users: 120 requests per minute
- Anonymous users: 30 requests per minute
- Burst allowance: 30 additional requests

Rate limiting can be configured via environment variables and supports both Redis-based distributed rate limiting and
in-memory rate limiting.

### Caching

Response caching is implemented to improve performance:

- TTL-based cache expiration
- ETag support for cache validation
- Thread-safe with lock-free reads and exclusive writes
- LRU (Least Recently Used) eviction policy
- Periodic cleanup of expired cache entries

### Retention Management

GDPR-compliant document retention management:

- Temporary files: 1 hour retention
- Redacted files: 24 hours retention
- Secure deletion with multiple overwrite patterns
- Background cleanup thread for expired files
- Graceful shutdown with cleanup

### Error Handling

Security-aware error handling to prevent information leakage:

- Sanitization of error messages to remove sensitive information
- Unique error IDs for traceability
- Detailed logging for debugging
- Safe error responses for clients

### Memory Management

Memory optimization to handle large documents:

- Memory usage monitoring
- Threshold-based optimization
- Garbage collection triggering
- Memory-optimized decorator for endpoints

### Session Encryption

All sensitive inputs and outputs can be protected end-to-end via AES-GCM:

- **Session mode**  
  - Headers: `session-key` + `api-key-id`  
  - All uploaded file payloads and form fields must be AES-GCM encrypted & base64-URL encoded.  
  - Responses are AES-GCM encrypted and base64-URL encoded in the `encrypted_data` JSON field.

- **Raw-API-Key mode**  
  - Header: `raw-api-key` (256-bit, URL-safe base64)  
  - Inputs may be encrypted or plaintext; any successful decryption triggers encrypted response.  
  - Encrypted responses returned in the `encrypted_data` field; otherwise raw data is streamed.

- **Public mode**  
  - No encryption or decryption applied; all data is plaintext.

Session encryption keys are rotated and stored securely; incorrect or missing keys yield HTTP 401 Unauthorized.

## Extending the System

### Adding a New Detection Engine

1. Create a new class that inherits from `EntityDetector` in `backend/app/entity_detection/base.py`
2. Implement the required methods:
    - `detect_sensitive_data()`
    - Any additional helper methods
3. Add the new engine to the `EntityDetectionEngine` enum in `backend/app/entity_detection/engines.py`
4. Create a configuration file for the new engine
5. Update the initialization service to initialize the new engine

### Adding a New API Endpoint

1. Create a new route function in the appropriate route file or create a new route file
2. Apply decorators for rate limiting and memory optimization as needed
3. Implement the endpoint logic using the appropriate services
4. Add error handling using `SecurityAwareErrorHandler`
5. Update the API documentation

### Adding Support for a New Document Type

1. Create a new extractor class that inherits from `DocumentExtractor`
2. Implement the required methods:
    - `extract_text()`
    - `close()`
3. Create a new redactor class that inherits from `DocumentRedactor`
4. Implement the required methods:
    - `apply_redactions()`
    - `close()`
5. Update the document processing services to support the new document type

## Dependencies

The project relies on the following key dependencies:

- **FastAPI**: Web framework for building APIs
- **Uvicorn**: ASGI server for running FastAPI
- **PyMuPDF**: PDF processing library
- **Presidio**: Microsoft's PII detection library
- **spaCy**: NLP library for entity recognition
- **Transformers**: Hugging Face's transformer models
- **Google Generative AI**: Google's Gemini API
- **GLiNER**: Entity recognition model
- **Redis**: Optional for distributed caching and rate limiting
- **SlowAPI**: Rate limiting for FastAPI
- **Pandas/NumPy**: Data processing

For a complete list of dependencies and versions, see `requirements.txt`.

## Additional Notes

### Performance Optimization

- Use batch processing for multiple files
- Enable caching for repeated operations
- Adjust `max_parallel_files` based on available resources
- Consider using Redis for distributed deployments

### Troubleshooting

- Check the logs for detailed error information
- Use the `/health` and `/metrics` endpoints to monitor system status
- Error IDs in responses can be used to trace issues in logs
- For memory issues, adjust the memory thresholds in configuration

### Production Deployment

- Use Docker Compose for easy deployment
- Configure Redis for distributed caching and rate limiting
- Set up proper monitoring and logging
- Use a reverse proxy like Nginx for SSL termination
- Consider using Kubernetes for scaling

### Security Best Practices

- Keep the API behind a secure network
- Use HTTPS for all communications
- Regularly update dependencies
- Monitor the `/metrics` endpoint for unusual activity
- Implement proper authentication for production use

