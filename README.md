# HideMeAI Backend

### Progress Report

Backend is under development, the following is the current status of the backend:

- ✅ API structure
- ✅ API routes
- ✅ API functionality
- 🔄 API testing
- 🔄 API documentation
- ✅ Presidio integration
- ✅ GLiNER integration
- ✅ Gemini integration
- ✅ Hybrid integration
- ✅ PDF processing
- ✅ Batch processing
- ✅ Memory management
- ✅ Rate limiting
- ✅ Error handling
- ✅ GDPR compliance
- ✅ Security measures
- ✅ Distributed tracing
- ✅ Performance optimization
- ✅ Configuration settings
- ✅ Docker setup
- ✅ Deployment scripts
- ✅ Logging and monitoring
- ✅ File and input validation
- ❌ Database integration
- ❌ User authentication
- ❌ User management and API endpoints
- 🔄 Multiple file formats support
- 🔄 Comprehensive testing suite
- ✅ CI/CD pipeline integration

- ⏳ Future enhancements to be determined

**Legend:**

- ✅ Completed
- 🔄 In Progress
- ❌ Not Started
- ⏳ Planned for Future

## Overview

HideMeAI is a secure document processing system designed to detect and redact sensitive information in various file
formats (primarily PDFs, but also DOCx and text files). The system combines multiple entity detection engines to
identify potentially sensitive information, following GDPR compliance guidelines with robust security measures.

## Core Components

### 1. Entity Detection Engines

The system uses three primary entity detection engines that can be used individually or combined through a hybrid
approach:

#### A. Presidio Entity Detector (`presidio.py`)

- Microsoft Presidio-based detection for standardized entity types
- Configured with custom rules especially for Norwegian formats
- Handles common entity types (email, phone numbers, identification numbers, etc.)
- Includes Norwegian-specific recognizers for `NO_FODSELSNUMMER`, `NO_PHONE_NUMBER`, etc.

#### B. GLiNER Entity Detector (`gliner.py`)

- Uses the GLiNER machine learning model for detecting a wide variety of entity types
- Model ID: "urchade/gliner_multi_pii-v1"
- Detects entities like names, addresses, identification numbers across many languages
- Features model caching and memory-optimized processing
- Special handling for Norwegian language pronouns to avoid false positives

#### C. Gemini Entity Detector (`gemini.py`)

- Uses Google's Gemini API for detecting entities
- Processes text with specialized prompts for entity detection
- Detects complex contextual entities and rare entity types
- Features advanced request throttling and quota management

#### D. Hybrid Entity Detector (`hybrid.py`)

- Combines results from multiple detection engines
- Can be configured to use any combination of engines
- Processes documents in parallel across engines
- Merges and deduplicates the entities detected by each engine

### 2. Document Processing

#### PDF Processing (`pdf.py`)

- Text extraction and position mapping from PDF documents
- Redaction capabilities to remove sensitive information
- Handles in-memory processing and streaming for large documents
- Supports page-by-page processing to optimize memory usage

### 3. Security & Performance Features

- **Memory Management**: Adaptive memory usage with resource monitoring
- **Buffer Pool**: Optimized buffer reuse to reduce memory allocation overhead
- **Rate Limiting**: Request throttling for API endpoints
- **Data Minimization**: GDPR-compliant data processing
- **Error Handling**: Secure error handling to prevent information leakage
- **File Validation**: Comprehensive content-type and signature validation
- **Secure Temporary Files**: Secure creation and deletion of temporary files
- **Processing Records**: GDPR-compliant audit trails without storing sensitive data

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

#### 2. Text Segmentation Algorithm (GLiNER)

GLiNER processes text in segments to handle token limits:

```
1. Split text into paragraphs
2. Group paragraphs into batches of appropriate size
3. For each text group:
   a. Process with GLiNER model
   b. Map detected entities back to original text positions
   c. Merge and deduplicate entities
```

#### 3. Entity Deduplication Algorithm

```
1. Create a unique key for each entity based on (entity_type, start, end)
2. For duplicate entities (same key), keep the one with highest confidence score
3. Remove overlapping entities using priority rules
```

#### 4. Redaction Mapping Algorithm

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
4. Deduplicate combined entities
5. Prepare unified redaction mapping
```

### File Processing & Memory Management

#### Streaming Large File Algorithm

```
1. For files > threshold:
   a. Process in chunks (64KB by default)
   b. Yield each chunk for processing
   c. Clear memory between chunks
2. For small files:
   a. Process entirely in memory
```

#### Adaptive Resource Allocation

```
1. Monitor system resources (CPU, memory)
2. Calculate optimal parallel workers based on:
   a. Available CPU cores
   b. Available memory
   c. Current memory pressure
   d. File sizes
3. Adjust thresholds based on system state
```

## PDF Lifecycle and Processing Scenarios

The system handles PDFs through different processing paths depending on file size, memory availability, and operation
type. Understanding these pathways is crucial for optimizing performance and resource usage.

### PDF Processing Lifecycle

1. **Intake Phase**
    - File upload validation (MIME type, size limits)
    - Initial security screening
    - Determination of processing strategy (in-memory vs. file-based)

2. **Text Extraction Phase**
    - Extraction of text with positional information
    - Creation of internal document representation
    - Application of data minimization rules

3. **Entity Detection Phase**
    - Processing through selected detection engines
    - Entity identification and classification
    - Creation of redaction mapping

4. **Redaction Phase**
    - Application of redaction boxes based on mapping
    - Generation of redacted document
    - Optional sanitization of document metadata

5. **Delivery Phase**
    - Streaming output to client
    - Cleanup of temporary resources
    - Recording of processing metrics

### Processing Scenarios

#### Scenario 1: Small PDF Processing (In-Memory)

- **Trigger**: PDF size < `IN_MEMORY_THRESHOLD` (default: 10MB)
- **Flow**:
    1. PDF loaded entirely into memory as byte array
    2. Text extraction performed directly on memory buffer
    3. Entity detection applied to extracted text
    4. Redaction applied directly in memory
    5. Resulting PDF streamed from memory to client
    6. No temporary files created, all processing in RAM
- **Benefits**: Faster processing, no I/O overhead, no cleanup required
- **Example**: A 2MB contract document processed entirely in RAM

```
Client -> API -> [Memory Buffer] -> Detection -> Redaction -> Client
```

#### Scenario 2: Medium PDF Processing (Hybrid Approach)

- **Trigger**: PDF size between `IN_MEMORY_THRESHOLD` and `LARGE_FILE_THRESHOLD` (10MB-50MB)
- **Flow**:
    1. PDF initially loaded into memory
    2. If memory pressure detected (>80%), content moved to secure temp file
    3. Text extraction performed, results kept in memory
    4. Entity detection applied to in-memory text representation
    5. Redaction applied, reading from temp file if created
    6. Output streamed to client
    7. Temp files securely deleted with overwriting
- **Benefits**: Balance between performance and memory usage
- **Example**: A 15MB report document with images

```
Client -> API -> [Memory/Temp File] -> Detection -> Redaction -> Client
                          |
                    [Secure Deletion]
```

#### Scenario 3: Large PDF Processing (Streaming)

- **Trigger**: PDF size > `LARGE_FILE_THRESHOLD` (default: 50MB)
- **Flow**:
    1. PDF content streamed to secure temporary file
    2. Text extraction performed page-by-page with streaming
    3. Entity detection applied to pages incrementally
    4. Redaction applied with page-based processing
    5. Output document streamed to client in chunks
    6. Temp files securely deleted with shredding
- **Benefits**: Minimal memory footprint, can handle very large files
- **Example**: A 100MB medical record with many pages and images

```
Client -> API -> [Temp File] -> [Page 1] -> Detection -> Redaction -> [Output Chunk 1] -> Client
                                [Page 2] -> Detection -> Redaction -> [Output Chunk 2] -> ...
                                    |
                            [Secure Deletion]
```

#### Scenario 4: Emergency Processing (Fallback Mode)

- **Trigger**: System under high memory pressure (>90%) or resource contention
- **Flow**:
    1. Immediate creation of temporary file regardless of PDF size
    2. Reduced parallelism and threading
    3. Simplified entity detection (may use only Presidio engine)
    4. Basic redaction without advanced features
    5. Output streamed with larger chunk size to reduce overhead
- **Benefits**: Ensures service availability under extreme load
- **Example**: System under high load processing multiple concurrent requests

```
Client -> API -> [Temp File] -> [Simplified Detection] -> [Basic Redaction] -> Client
                                          |
                                  [Secure Deletion]
```

### Key Decision Points

The system determines the processing path based on these factors:

1. **File Size Check**
   ``` python
   use_in_memory = file_size < IN_MEMORY_THRESHOLD
   use_streaming = file_size > LARGE_FILE_THRESHOLD
   ```

2. **Memory Pressure Check**
   ``` python
   if memory_monitor.get_memory_usage() > MEMORY_THRESHOLD:
       # Fall back to file-based processing even for smaller files
       use_in_memory = False
   ```

3. **Resource Contention Check**
   ``` python
   # Using the AsyncTimeoutLock for controlled resource access
   async with pdf_lock.acquire_timeout(timeout=10.0) as acquired:
       if not acquired:
           # Fall back to emergency processing path
   ```

4. **Processing Time Optimization**
   ``` python
   # For entity detection, adjust timeout based on file size
   timeout = min(30.0 + (file_size / (1024 * 1024) * 2), 120.0)  # 30s base + 2s per MB, max 120s
   ```

### Performance Impact

The table below shows approximate performance metrics for different PDF sizes:

| PDF Size | Processing Mode | Memory Usage | Processing Time | Temp Files |
|----------|-----------------|--------------|-----------------|------------|
| 1MB      | In-Memory       | ~10MB        | 1-2s            | None       |
| 10MB     | Hybrid          | ~50MB        | 5-10s           | Sometimes  |
| 50MB     | Streaming       | ~100MB       | 20-40s          | Always     |
| 100MB+   | Streaming       | ~150MB       | 60s+            | Always     |

## Configuration Settings

### Environment Variables

| Variable                     | Description                                     | Default                                   |
|------------------------------|-------------------------------------------------|-------------------------------------------|
| `MEMORY_THRESHOLD`           | Memory usage percentage threshold for cleanup   | `80.0`                                    |
| `CRITICAL_MEMORY_THRESHOLD`  | Critical memory threshold for emergency cleanup | `90.0`                                    |
| `MEMORY_CHECK_INTERVAL`      | Interval for memory checks (seconds)            | `5.0`                                     |
| `ENABLE_MEMORY_MONITORING`   | Enable memory monitoring                        | `true`                                    |
| `ADAPTIVE_MEMORY_THRESHOLDS` | Adapt thresholds based on system resources      | `true`                                    |
| `MAX_PDF_SIZE_BYTES`         | Maximum PDF file size in bytes                  | `25 * 1024 * 1024` (25MB)                 |
| `MAX_TEXT_SIZE_BYTES`        | Maximum text file size in bytes                 | `10 * 1024 * 1024` (10MB)                 |
| `MAX_DOCX_SIZE_BYTES`        | Maximum DOCX file size in bytes                 | `20 * 1024 * 1024` (20MB)                 |
| `MAX_BATCH_SIZE_BYTES`       | Maximum batch processing size in bytes          | `50 * 1024 * 1024` (50MB)                 |
| `MAX_FILE_COUNT`             | Maximum number of files in a batch              | `20`                                      |
| `IN_MEMORY_THRESHOLD`        | Size threshold for in-memory processing         | `10485760` (10MB)                         |
| `MAX_BUFFER_POOL_SIZE`       | Maximum memory for buffer pooling               | `52428800` (50MB)                         |
| `USE_BUFFER_POOL`            | Enable buffer pooling                           | `true`                                    |
| `RANDOMIZE_FILENAMES`        | Add random suffix to sanitized filenames        | `false`                                   |
| `BLOCK_PDF_JAVASCRIPT`       | Block PDFs containing JavaScript                | `false`                                   |
| `BLOCK_OFFICE_MACROS`        | Block Office documents with macros              | `true`                                    |
| `VALIDATE_ZIP_CONTENTS`      | Validate content of ZIP files                   | `true`                                    |
| `ERROR_LOG_PATH`             | Path for detailed error logs                    | `app/logs/error_logs/detailed_errors.log` |
| `ERROR_JSON_LOGGING`         | Use JSON format for error logging               | `true`                                    |
| `ENABLE_DISTRIBUTED_TRACING` | Enable distributed tracing                      | `false`                                   |
| `SERVICE_NAME`               | Service name for tracing                        | `document_processing`                     |
| `REDIS_URL`                  | Redis URL for distributed rate limiting         | None                                      |
| `RATE_LIMIT_RPM`             | Requests per minute for rate limiting           | `60`                                      |
| `ADMIN_RATE_LIMIT_RPM`       | Admin requests per minute                       | `120`                                     |
| `ANON_RATE_LIMIT_RPM`        | Anonymous requests per minute                   | `30`                                      |
| `RATE_LIMIT_BURST`           | Burst allowance for rate limiting               | `10`                                      |
| `GLINER_MODEL_DIR`           | Directory for GLiNER model storage              | `{base}/models/gliner`                    |
| `EXTRACTION_DEBUG`           | Enable debug logging for extraction             | `false`                                   |

### GLiNER Configuration

``` python
# Located in gliner_config.py
GLINER_MODEL_NAME = "urchade/gliner_multi_pii-v1"
GLINER_MODEL_DIR = os.environ.get("GLINER_MODEL_DIR", os.path.join(...))
GLINER_MODEL_PATH = os.path.join(GLINER_MODEL_DIR, "gliner_multi_pii-v1.pt")
```

### GDPR Configuration

``` python
# Located in gdpr_config.py
TEMP_FILE_RETENTION_SECONDS = 3600  # 1 hour
REDACTED_FILE_RETENTION_SECONDS = 86400  # 24 hours
LEGAL_BASIS = "legitimate_interest"
DATA_MINIMIZATION_RULES = {
    "keep_metadata": False,
    "strip_document_authors": True,
    "strip_timestamp": True,
    "required_fields_only": True,
}
MAX_DETECTOR_CACHE_SIZE = 1000
```

### Memory Management Parameters

``` python
# In memory_management.py
MAX_PARALLELISM = 12  # Hard limit on parallelism regardless of cores
DEFAULT_TIMEOUT = 300.0  # Default timeout for batch processing (5 minutes)
MIN_MEMORY_PER_WORKER = 250 * 1024 * 1024  # 250 MB per worker minimum
MAX_MEMORY_PERCENTAGE = 80  # Maximum percentage of memory to use
```

### Batch Processing Parameters

``` python
# In batch_processing_helper.py
MAX_PARALLELISM = 12
DEFAULT_TIMEOUT = 300.0  # 5 minutes
MIN_MEMORY_PER_WORKER = 250 * 1024 * 1024  # 250 MB
MAX_MEMORY_PERCENTAGE = 80
```

### Security Parameters

File validation thresholds are defined in `file_validation.py`:

``` python
MAX_PDF_SIZE_BYTES = 25 * 1024 * 1024  # 25MB
MAX_TEXT_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_DOCX_SIZE_BYTES = 20 * 1024 * 1024  # 20MB
MAX_BATCH_SIZE_BYTES = 50 * 1024 * 1024  # 50MB
MAX_FILE_COUNT = 20
```

## Folder Structure

```
backend/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── ai_routes.py
│   │   │   ├── batch_routes.py
│   │   │   ├── machine_learning.py
│   │   │   ├── hybrid_routes.py
│   │   │   ├── metadata_routes.py
│   │   │   ├── pdf_routes.py
│   │   │   └── status_routes.py
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── models.py
│   ├── configs/
│   │   ├── __init__.py
│   │   ├── analyzer-config.yml
│   │   ├── config_singleton.py
│   │   ├── gdpr_config.py
│   │   ├── gemini_config.py
│   │   ├── gliner_config.py
│   │   ├── nlp-config.yml
│   │   ├── presidio_config.py
│   │   └── recognizers-config.yml
│   ├── document_processing/
│   │   ├── __init__.py
│   │   └── pdf.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── interfaces.py
│   │   └── models.py
│   ├── entity_detection/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── gemini.py
│   │   ├── gliner.py
│   │   ├── hybrid.py
│   │   └── presidio.py
│   ├── factory/
│   │   ├── __init__.py
│   │   └── document_processing_factory.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── batch_processing_service.py
│   │   ├── configuration.py
│   │   ├── document_processing.py
│   │   └── initialization_service.py
│   └── utils/ (to be refactored into separate modules)
│       ├── __init__.py
│       ├── batch_processing_utils.py
│       ├── buffer_pool.py
│       ├── caching_middleware.py
│       ├── common_detection.py
│       ├── data_minimization.py
│       ├── document_processing_utils.py
│       ├── error_handling.py
│       ├── file_validation.py
│       ├── logger.py
│       ├── memory_management.py
│       ├── processing_records.py
│       ├── rate_limiting.py
│       ├── retention_management.py
│       ├── sanitize_utils.py
│       ├── secure_file_utils.py
│       ├── secure_logging.py
│       ├── synchronization_utils.py
│       └── helpers/
│           ├── __init__.py
│           ├── batch_processing_helper.py
│           ├── gemini_helper.py
│           ├── gemini_usage_manager.py
│           ├── hybrid_detection_helper.py
│           ├── json_helper.py
│           ├── ml_models_helper.py
│           ├── parallel_helper.py
│           └── text_utils.py
├── models/
├── logs/
├── requirements.txt
├── main.py
├── Dockerfile
├── docker-compose.yml
└── .env  
```

## API Routes and Endpoints

The HideMeAI backend exposes several RESTful endpoints organized by functionality. Each endpoint is designed with memory
optimization, error handling, and rate limiting in mind.

### System Status Endpoints

#### Basic Status Check

```
GET /status
```

**Description**: Provides basic status information about the API.

**Response**:

```json
{
  "status": "success",
  "timestamp": 1709372851.456789,
  "api_version": "1.0.0"
}
```

**Rate Limit**: 60 requests per minute

#### Health Check

```
GET /health
```

**Description**: Provides detailed health information about the system, including CPU usage, memory usage, and service
status.

**Response**:

```json
{
  "status": "healthy",
  "timestamp": 1709372851.456789,
  "services": {
    "api": "online",
    "document_processing": "online"
  },
  "process": {
    "cpu_percent": 12.5,
    "memory_percent": 34.2,
    "threads_count": 8,
    "uptime": 3600.5
  },
  "memory": {
    "current_usage": 45.3,
    "peak_usage": 67.8,
    "last_check": 1709372841.123456
  },
  "cache": {
    "cache_size": 15,
    "cached_endpoints": [
      "api_status",
      "entities_list"
    ]
  }
}
```

**Rate Limit**: 30 requests per minute

#### Performance Metrics

```
GET /metrics
```

**Description**: Provides detailed performance metrics for monitoring. Requires an API key.

**Headers**:

- `X-API-Key`: Required for authentication

**Response**:

```json
{
  "timestamp": 1709372851.456789,
  "system": {
    "cpu_percent": 15.7,
    "memory_percent": 67.2,
    "memory_available": 4294967296,
    "memory_total": 8589934592
  },
  "process": {
    "cpu_percent": 12.5,
    "memory_rss": 536870912,
    "memory_percent": 6.25,
    "threads_count": 8,
    "open_files": 24,
    "connections": 12
  },
  "memory_monitor": {
    "current_usage": 45.3,
    "peak_usage": 67.8,
    "cleanup_count": 3
  },
  "cache": {
    "cache_size": 15,
    "cache_keys": 15
  }
}
```

**Rate Limit**: 15 requests per minute

#### Readiness Check

```
GET /readiness
```

**Description**: Used by load balancers to determine if the service is ready to accept requests.

**Response** (status code 200 if ready, 503 if not ready):

```json
{
  "ready": true,
  "services": {
    "presidio_ready": true,
    "gemini_ready": true,
    "gliner_ready": true
  },
  "memory": {
    "usage_percent": 65.7,
    "status": "ok"
  }
}
```

**Rate Limit**: 60 requests per minute

### Entity Detection Endpoints

#### Presidio Detection

```
POST /ml/detect
```

**Description**: Detects sensitive information using Microsoft's Presidio NER engine, which is optimized for standard
PII patterns.

**Form Data**:

- `file`: The document file to process (PDF, text, etc.)
- `requested_entities` (optional): Comma-separated list of entity types to detect

**Response**:

```json
{
    "redaction_mapping": {
        "pages": [
            {
                "page": 1,
                "sensitive": [
                    {
                        "original_text": "Jeanett Lofthagen",
                        "entity_type": "PERSON",
                        "start": 91,
                        "end": 108,
                        "score": 0.85,
                        "bbox": {
                            "x0": 283.909912109375,
                            "y0": 789.9979858398438,
                            "x1": 351.92486572265625,
                            "y1": 795.3807983398438
                        }
                    },
                    {
                        "original_text": "Jeanett Lofthagen",
                        "entity_type": "PERSON",
                        "start": 400,
                        "end": 417,
                        "score": 0.85,
                        "bbox": {
                            "x0": 364.2444152832031,
                            "y0": 313.8487548828125,
                            "x1": 452.3438415527344,
                            "y1": 322.1804504394531
                        }
                    },
                    {
                        "original_text": "Synnøve Goli Ellingstad",
                        "entity_type": "PERSON",
                        "start": 357,
                        "end": 380,
                        "score": 0.85,
                        "bbox": {
                            "x0": 150.86439514160156,
                            "y0": 313.8487548828125,
                            "x1": 267.67254638671875,
                            "y1": 322.1804504394531
                        }
                    },
                    {
                        "original_text": "Simen Vien Østdahl",
                        "entity_type": "PERSON",
                        "start": 445,
                        "end": 463,
                        "score": 0.85,
                        "bbox": {
                            "x0": 141.14251708984375,
                            "y0": 326.5687561035156,
                            "x1": 238.3805694580078,
                            "y1": 334.90045166015625
                        }
                    },
                    {
                        "original_text": "TSE-prøver",
                        "entity_type": "PERSON",
                        "start": 779,
                        "end": 789,
                        "score": 0.85,
                        "bbox": {
                            "x0": 241.4066619873047,
                            "y0": 441.04876708984375,
                            "x1": 298.2532958984375,
                            "y1": 449.3804626464844
                        }
                    }
                ]
            },
            {
                "page": 2,
                "sensitive": [
                    {
                        "original_text": "Vera",
                        "entity_type": "PERSON",
                        "start": 885,
                        "end": 889,
                        "score": 0.85,
                        "bbox": {
                            "x0": 291.4853210449219,
                            "y0": 343.3687744140625,
                            "x1": 317.7847900390625,
                            "y1": 351.7004699707031
                        }
                    },
                    {
                        "original_text": "Karl Ove Stadheim Jensen",
                        "entity_type": "PERSON",
                        "start": 2308,
                        "end": 2332,
                        "score": 0.85,
                        "bbox": {
                            "x0": 70.800048828125,
                            "y0": 710.0887451171875,
                            "x1": 201.71017456054688,
                            "y1": 718.42041015625
                        }
                    }
                ]
            }
        ]
    },
    "entities_detected": {
        "total": 7,
        "by_type": {
            "PERSON": 7
        },
        "by_page": {
            "page_1": 5,
            "page_2": 2
        }
    },
    "performance": {
        "file_read_time": 0.0,
        "extraction_time": 0.019001007080078125,
        "detector_init_time": 0,
        "detection_time": 0.6280515193939209,
        "total_time": 0.651054859161377,
        "words_count": 613,
        "pages_count": 2,
        "entity_density": 11.419249592169658,
        "sanitize_time": 0.0
    },
    "file_info": {
        "filename": "Inspeksjonsrapport med skriftlig veiledning.pdf",
        "content_type": "application/pdf",
        "size": "0.07 MB"
    },
    "model_info": {
        "engine": "presidio"
    },
    "_debug": {
        "memory_usage": 5.640750038473376,
        "peak_memory": 22.677722953216374,
        "operation_id": "presidio_detect_1743251687"
    }
}
```

**Rate Limit**: 10 requests per minute

#### GLiNER Detection

```
POST /ml/gl_detect
```

**Description**: Detects sensitive information using the GLiNER machine learning model, which is effective at detecting
complex entity types that traditional NER systems might miss.

**Form Data**:

- `file`: The document file to process (PDF, text, etc.)
- `requested_entities` (optional): Comma-separated list of entity types to detect

**Response**: Similar to Presidio detection but with `"engine": "gliner"`

**Rate Limit**: 10 requests per minute

#### Gemini AI Detection

```
POST /ai/detect
```

**Description**: Detects sensitive information using Google's Gemini AI API, which can identify complex contextual
entities.

**Form Data**:

- `file`: The document file to process (PDF, text, etc.)
- `requested_entities` (optional): Comma-separated list of entity types to detect

**Response**: Similar to Presidio detection but with `"engine": "gemini"`

**Rate Limit**: 10 requests per minute


### PDF Processing Endpoints

#### PDF Text Extraction

```
POST /pdf/extract
```

**Description**: Extracts text with positions from a PDF file, optimized for memory efficiency with large files.

**Form Data**:

- `file`: The PDF file to process

**Response**:

```json
{
  "pages": [
    {
      "page": 1,
      "words": [
        {
          "text": "Example",
          "x0": 100,
          "y0": 200,
          "x1": 150,
          "y1": 220
        }
      ]
    }
  ],
   "performance": {
        "file_read_time": 0.0,
        "extraction_time": 0.012547731399536133,
        "total_time": 0.018546104431152344,
        "pages_count": 2,
        "words_count": 613,
        "operation_id": "pdf_extract_1743252072.9976451"
    },
    "file_info": {
        "filename": "Inspeksjonsrapport med skriftlig veiledning.pdf",
        "content_type": "application/pdf",
        "size": "0.07 MB"
    }
}
```

**Rate Limit**: 15 requests per minute

#### PDF Redaction

```
POST /pdf/redact
```

**Description**: Applies redactions to a PDF file based on a provided redaction mapping.

**Form Data**:

- `file`: The PDF file to process
- `redaction_mapping`: JSON string containing the positions to redact
- `remove_images`:  Boolean whether to redact all images in the file. (Default false)


**Response**: The redacted PDF file as a stream with the following headers:

- `Content-Disposition`: "attachment; filename=redacted.pdf"
- `X-Redaction-Time`: Processing time in seconds
- `X-Total-Time`: Total request time in seconds
- `X-Redactions-Applied`: Number of redactions applied
- `X-Memory-Usage`: Current memory usage percentage
- `X-Peak-Memory`: Peak memory usage percentage
- `X-Operation-ID`: Unique operation identifier

**Rate Limit**: 10 requests per minute

### Batch Processing Endpoints

#### Batch Entity Detection

```
POST /batch/detect
```

**Description**: Processes multiple files for entity detection in parallel.

**Form Data**:

- `files`: List of files to process
- `requested_entities` (optional): Comma-separated list of entity types to detect
- `detection_engine` (optional): Engine to use ("presidio", "gemini", "gliner")
- `max_parallel_files` (optional): Maximum number of files to process in parallel

**Response**:

``` json

{
    "batch_summary": {
        "batch_id": "5c460d55-914e-4021-8c3f-83074a71b02c",
        "total_files": 2,
        "successful": 2,
        "failed": 0,
        "total_time": 1.2733795642852783,
        "workers": 4
    },
    "file_results": [
        {
            "file": "Inspeksjonsrapport-2.pdf",
            "status": "success",
            "results": {
                "redaction_mapping": {
                    "pages": [
                        {
                            "page": 1,
                            "sensitive": [
                                {
                                    "original_text": "Astrid Holm",
                                    "entity_type": "PERSON",
                                    "start": 15,
                                    "end": 26,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 147.44161987304688,
                                        "y0": 72.75343322753906,
                                        "x1": 203.49172973632812,
                                        "y1": 82.2332763671875
                                    }
                                },
                                {
                                    "original_text": "Astrid Holm",
                                    "entity_type": "PERSON",
                                    "start": 314,
                                    "end": 325,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 147.32015991210938,
                                        "y0": 146.8134307861328,
                                        "x1": 203.3813018798828,
                                        "y1": 156.29327392578125
                                    }
                                },
                                {
                                    "original_text": "Eva Hansen",
                                    "entity_type": "PERSON",
                                    "start": 284,
                                    "end": 294,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 437.5617370605469,
                                        "y0": 132.2934112548828,
                                        "x1": 493.5455627441406,
                                        "y1": 141.77325439453125
                                    }
                                },
                                {
                                    "original_text": "Kari Nordmann",
                                    "entity_type": "PERSON",
                                    "start": 367,
                                    "end": 380,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 401.6597595214844,
                                        "y0": 146.8134307861328,
                                        "x1": 476.5109558105469,
                                        "y1": 156.29327392578125
                                    }
                                },
                                {
                                    "original_text": "Kontrollpunkter",
                                    "entity_type": "PERSON",
                                    "start": 1431,
                                    "end": 1446,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 70.8239974975586,
                                        "y0": 426.6834411621094,
                                        "x1": 150.4776153564453,
                                        "y1": 436.16326904296875
                                    }
                                },
                                {
                                    "original_text": "HMS-rutiner",
                                    "entity_type": "PERSON",
                                    "start": 1515,
                                    "end": 1526,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 106.81999969482422,
                                        "y0": 471.70343017578125,
                                        "x1": 164.85919189453125,
                                        "y1": 481.1832580566406
                                    }
                                }
                            ]
                        },
                        {
                            "page": 2,
                            "sensitive": []
                        },
                        {
                            "page": 3,
                            "sensitive": [
                                {
                                    "original_text": "Astrid Holm",
                                    "entity_type": "PERSON",
                                    "start": 361,
                                    "end": 372,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 70.8239974975586,
                                        "y0": 289.7634582519531,
                                        "x1": 127.1169662475586,
                                        "y1": 299.2432861328125
                                    }
                                }
                            ]
                        }
                    ]
                },
                "entities_detected": {
                    "total": 6,
                    "by_type": {
                        "PERSON": 6
                    },
                    "by_page": {
                        "page_1": 6,
                        "page_2": 0,
                        "page_3": 1
                    }
                },
                "performance": {
                    "words_count": 745,
                    "pages_count": 3,
                    "entity_density": 8.053691275167786,
                    "sanitize_time": 0.0
                },
                "file_info": {
                    "filename": "Inspeksjonsrapport-2.pdf",
                    "content_type": "application/pdf",
                    "size": "0.06 MB"
                },
                "model_info": {
                    "engine": "PRESIDIO"
                }
            }
        },
        {
            "file": "Inspeksjonsrapport-3.pdf",
            "status": "success",
            "results": {
                "redaction_mapping": {
                    "pages": [
                        {
                            "page": 1,
                            "sensitive": [
                                {
                                    "original_text": "Lars Mikkelsen",
                                    "entity_type": "PERSON",
                                    "start": 91,
                                    "end": 105,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 147.44161987304688,
                                        "y0": 101.81343078613281,
                                        "x1": 217.8105926513672,
                                        "y1": 111.29327392578125
                                    }
                                },
                                {
                                    "original_text": "AS Storgata",
                                    "entity_type": "PERSON",
                                    "start": 258,
                                    "end": 269,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 182.0188751220703,
                                        "y0": 233.6934356689453,
                                        "x1": 195.34414672851562,
                                        "y1": 243.17327880859375
                                    }
                                },
                                {
                                    "original_text": "AS Storgata",
                                    "entity_type": "PERSON",
                                    "start": 258,
                                    "end": 269,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 70.8239974975586,
                                        "y0": 248.21339416503906,
                                        "x1": 110.97648620605469,
                                        "y1": 257.6932373046875
                                    }
                                },
                                {
                                    "original_text": "Ingrid Bergman",
                                    "entity_type": "PERSON",
                                    "start": 491,
                                    "end": 505,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 402.6090393066406,
                                        "y0": 388.1634216308594,
                                        "x1": 474.2696228027344,
                                        "y1": 397.64324951171875
                                    }
                                },
                                {
                                    "original_text": "Ola Nordmann",
                                    "entity_type": "PERSON",
                                    "start": 525,
                                    "end": 537,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 147.32015991210938,
                                        "y0": 402.6834411621094,
                                        "x1": 217.34686279296875,
                                        "y1": 412.16326904296875
                                    }
                                },
                                {
                                    "original_text": "Erik Hjermelund",
                                    "entity_type": "PERSON",
                                    "start": 578,
                                    "end": 593,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 412.7101135253906,
                                        "y0": 402.6834411621094,
                                        "x1": 488.95233154296875,
                                        "y1": 412.16326904296875
                                    }
                                },
                                {
                                    "original_text": "Erik Hjermelund",
                                    "entity_type": "PERSON",
                                    "start": 1330,
                                    "end": 1345,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 70.8239974975586,
                                        "y0": 722.5333862304688,
                                        "x1": 147.19871520996094,
                                        "y1": 732.0132446289062
                                    }
                                },
                                {
                                    "original_text": "Markus Hjermelund",
                                    "entity_type": "PERSON",
                                    "start": 608,
                                    "end": 625,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 125.26223754882812,
                                        "y0": 417.20343017578125,
                                        "x1": 222.09408569335938,
                                        "y1": 426.6832580566406
                                    }
                                },
                                {
                                    "original_text": "Markus Hjermelund",
                                    "entity_type": "PERSON",
                                    "start": 1486,
                                    "end": 1503,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 365.647216796875,
                                        "y0": 737.0494384765625,
                                        "x1": 462.3575744628906,
                                        "y1": 746.529296875
                                    }
                                }
                            ]
                        },
                        {
                            "page": 2,
                            "sensitive": [
                                {
                                    "original_text": "Kontrollpunkter",
                                    "entity_type": "PERSON",
                                    "start": 0,
                                    "end": 15,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 70.8239974975586,
                                        "y0": 72.75343322753906,
                                        "x1": 150.4776153564453,
                                        "y1": 82.2332763671875
                                    }
                                },
                                {
                                    "original_text": "A. Pedersen",
                                    "entity_type": "PERSON",
                                    "start": 950,
                                    "end": 961,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 122.72303771972656,
                                        "y0": 532.6633911132812,
                                        "x1": 182.65924072265625,
                                        "y1": 542.1432495117188
                                    }
                                },
                                {
                                    "original_text": "K. Johansen",
                                    "entity_type": "PERSON",
                                    "start": 965,
                                    "end": 976,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 198.61204528808594,
                                        "y0": 532.6633911132812,
                                        "x1": 258.31634521484375,
                                        "y1": 542.1432495117188
                                    }
                                },
                                {
                                    "original_text": "Erik Hjermelund",
                                    "entity_type": "PERSON",
                                    "start": 1027,
                                    "end": 1042,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 484.2941589355469,
                                        "y0": 532.6633911132812,
                                        "x1": 502.035400390625,
                                        "y1": 542.1432495117188
                                    }
                                },
                                {
                                    "original_text": "Erik Hjermelund",
                                    "entity_type": "PERSON",
                                    "start": 1027,
                                    "end": 1042,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 70.8239974975586,
                                        "y0": 547.1834106445312,
                                        "x1": 127.16112518310547,
                                        "y1": 556.6632690429688
                                    }
                                },
                                {
                                    "original_text": "Gnager-ekskrementer",
                                    "entity_type": "PERSON",
                                    "start": 1429,
                                    "end": 1448,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 70.8239974975586,
                                        "y0": 732.1334228515625,
                                        "x1": 174.6761474609375,
                                        "y1": 741.61328125
                                    }
                                },
                                {
                                    "original_text": "Markus Hjermelund",
                                    "entity_type": "PERSON",
                                    "start": 1470,
                                    "end": 1487,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 269.0570373535156,
                                        "y0": 732.1334228515625,
                                        "x1": 362.6982727050781,
                                        "y1": 741.61328125
                                    }
                                }
                            ]
                        },
                        {
                            "page": 3,
                            "sensitive": [
                                {
                                    "original_text": "Nina Solberg",
                                    "entity_type": "PERSON",
                                    "start": 352,
                                    "end": 364,
                                    "score": 0.85,
                                    "bbox": {
                                        "x0": 70.8239974975586,
                                        "y0": 310.7634582519531,
                                        "x1": 131.55503845214844,
                                        "y1": 320.2432861328125
                                    }
                                }
                            ]
                        }
                    ]
                },
                "entities_detected": {
                    "total": 14,
                    "by_type": {
                        "PERSON": 14
                    },
                    "by_page": {
                        "page_1": 9,
                        "page_2": 7,
                        "page_3": 1
                    }
                },
                "performance": {
                    "words_count": 475,
                    "pages_count": 3,
                    "entity_density": 29.473684210526315,
                    "sanitize_time": 0.0
                },
                "file_info": {
                    "filename": "Inspeksjonsrapport-3.pdf",
                    "content_type": "application/pdf",
                    "size": "0.07 MB"
                },
                "model_info": {
                    "engine": "PRESIDIO"
                }
            }
        }
    ],
}

```

**Rate Limit**: 10 requests per minute

#### Batch Document Redaction

```
POST /batch/redact
```

**Description**: Applies redactions to multiple documents in parallel and returns them as a ZIP file.

**Form Data**:

- `files`: List of files to process
- `redaction_mappings`: JSON string containing the redaction mappings for each file
- `max_parallel_files` (optional): Maximum number of files to process in parallel
- `remove_images`:  Boolean whether to redact all images in the file. (Default false)

**Response**: ZIP file containing all redacted documents with the following headers:

- `Content-Disposition`: "attachment; filename=redacted_documents.zip"
- `X-Redaction-Time`: Processing time in seconds
- `X-Total-Time`: Total request time in seconds
- `X-Files-Processed`: Number of files processed
- `X-Operation-ID`: Unique operation identifier

**Rate Limit**: 3 requests per minute

#### Batch Hybrid Detection

```
POST /batch/hybrid_detect
```

**Description**: Processes multiple files using hybrid detection across multiple engines.

**Form Data**:

- `files`: List of files to process
- `requested_entities` (optional): Comma-separated list of entity types to detect
- `use_presidio` (optional): Boolean flag to enable Presidio (default: true)
- `use_gemini` (optional): Boolean flag to enable Gemini (default: true)
- `use_gliner` (optional): Boolean flag to enable GLiNER (default: false)
- `max_parallel_files` (optional): Maximum number of files to process in parallel

**Response**: Similar to batch detection but with hybrid engine information

**Rate Limit**: 10 requests per minute

#### Batch Text Extraction

```
POST /batch/search
```

**Description**: Extracts text with positions from multiple files in parallel.

**Form Data**:

- `files`: List of files to process
- `max_parallel_files` (optional): Maximum number of files to process in parallel

**Response**:

``` json
{
  "batch_summary": {
    "total_files": 3,
    "successful": 3,
    "failed": 0,
    "total_pages": 15,
    "total_words": 7500,
    "total_time": 1.567,
    "workers": 3,
    "operation_id": "batch_extract_1709372851",
    "lock_used": true
  },
  "file_results": [
    {
      "file": "document1.pdf",
      "status": "success",
      "results": {
        "pages": [
          {
            "page": 1,
            "words": [/* Word objects with positions */]
          }
        ],
         "empty_pages": [],
    "total_document_pages": 2,
    "content_pages": 2,
    "_minimization_meta": {
        "applied_at": 1743252073.0151935,
        "required_fields_only": true,
        "fields_retained": [
            "empty_pages",
            "total_document_pages",
            "content_pages"
        ]
    },
         "performance": {
        "file_read_time": 0.0,
        "extraction_time": 0.012547731399536133,
        "total_time": 0.018546104431152344,
        "pages_count": 2,
        "words_count": 613,
        "operation_id": "pdf_extract_1743252072.9976451"
    },
    "file_info": {
        "filename": "document1.pdf",
        "content_type": "application/pdf",
        "size": "0.07 MB"
    },
    /* Results for additional files */
  ]
}
```

**Rate Limit**: 15 requests per minute

### Metadata Endpoints

#### Available Detection Engines

```
GET /help/engines
```

**Description**: Lists all available entity detection engines.

**Response**:

```json
{
  "engines": [
    "PRESIDIO",
    "GEMINI",
    "GLINER",
    "HYBRID"
  ]
}
```

**Rate Limit**: 30 requests per minute

#### Available Entity Types

```
GET /help/entities
```

**Description**: Lists all available entity types that can be detected.

**Response**:

``` json
{
  "presidio_entities": ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "ADDRESS", "DATE", "US_SSN", "LOCATION", "ORGANIZATION"],
  "gemini_entities": {
    "PERSON": "Names of individuals",
    "EMAIL_ADDRESS": "Email addresses",
    /* Additional entity types and descriptions */
  },
  "gliner_entities": ["PERSON", "EMAIL", "PHONE", "ADDRESS", "ID_NUMBER", "CREDIT_CARD", "MEDICAL_RECORD", "BANK_ACCOUNT"]
}
```

**Rate Limit**: 20 requests per minute

#### Entity Examples

```
GET /help/entity-examples
```

**Description**: Provides examples of each entity type.

**Response**:

``` json
{
  "examples": {
    "PERSON": ["John Doe", "Jane Smith", "Dr. Robert Johnson"],
    "EMAIL_ADDRESS": ["john.doe@example.com", "contact@company.org"],
    "PHONE_NUMBER": ["+1 (555) 123-4567", "555-987-6543"],
    /* Examples for additional entity types */
  }
}
```

**Rate Limit**: 30 requests per minute

#### Detector Status

```
GET /help/detectors-status
```

**Description**: Provides the current status of all detector instances.

**Response**:

``` json
{
  "presidio": {
    "initialized": true,
    "uses": 250,
    "last_used": 1709372841.123456,
    "cache_size": 5
  },
  "gemini": {
    "initialized": true,
    "uses": 120,
    "quota_remaining": 4800,
    "last_used": 1709372801.456789
  },
  "gliner": {
    "initialized": true,
    "uses": 85,
    "model_loaded": true,
    "last_used": 1709372821.789012
  },
  "_meta": {
    "last_updated": "2023-03-01T12:34:56.789",
    "cache_ttl": 60
  }
}
```

**Rate Limit**: 10 requests per minute

#### API Routes

```
GET /help/routes
```

**Description**: Provides a comprehensive overview of all available API routes.

**Response**:

``` json
{
  "entity_detection": [
    {
      "path": "/hybrid/detect",
      "method": "POST",
      "description": "Hybrid entity detection across multiple engines",
      "engines": ["Presidio", "Gemini", "GLiNER"]
    },
    /* Additional entity detection routes */
  ],
  "batch_processing": [
    {
      "path": "/batch/detect",
      "method": "POST",
      "description": "Batch entity detection"
    },
    /* Additional batch processing routes */
  ],
  "pdf_processing": [
    {
      "path": "/pdf/redact",
      "method": "POST",
      "description": "PDF document redaction"
    },
    /* Additional PDF processing routes */
  ],
  "metadata": [
    {
      "path": "/help/engines",
      "method": "GET",
      "description": "List available detection engines"
    },
    /* Additional metadata routes */
  ],
  "system": [
    {
      "path": "/status",
      "method": "GET",
      "description": "Basic API status"
    },
    /* Additional system routes */
  ]
}
```

**No Rate Limit**

## Performance Optimization

### Memory Optimizations

1. **Buffer Pooling**: Reduces memory allocation/deallocation overhead
    - `USE_BUFFER_POOL`: Enable/disable (default: true)
    - `MAX_BUFFER_POOL_SIZE`: Maximum pool size (default: 50MB)

2. **Streaming Processing**: Handles large files without loading entirely in memory
    - `IN_MEMORY_THRESHOLD`: Size threshold for in-memory vs. file-based processing (default: 10MB)

3. **Batch Processing**: Processes files in batches with resource-aware parallelism
    - `MAX_PARALLELISM`: Maximum parallel tasks (default: 12)
    - Automatically adjusts based on system resources

4. **Adaptive Memory Management**:
    - `MEMORY_THRESHOLD`: Triggers cleanup when memory usage exceeds this percentage (default: 80%)
    - `CRITICAL_MEMORY_THRESHOLD`: Triggers emergency cleanup (default: 90%)

### Caching

1. **Model Caching**: GLiNER models are cached for reuse
    - `MAX_DETECTOR_CACHE_SIZE`: Maximum cached detector instances (default: 1000)

2. **Response Caching**: API responses can be cached (via `caching_middleware.py`)
    - Default TTL: 300 seconds (5 minutes)

## Important Relationships

1. **Entity Detection Flow**:
   ```
   BaseEntityDetector
    ↓
    ├── PresidioEntityDetector
    ├── GlinerEntityDetector 
    ├── GeminiEntityDetector
    └── HybridEntityDetector (combines the others)
   ```

2. **Document Processing Flow**:
   ```
   DocumentProcessingService
    ↓
    ├── Extraction (PDFTextExtractor)
    ├── Entity Detection (via InitializationService)
    └── Redaction (PDFRedactionService)
   ```

3. **Batch Processing Flow**:
   ```
   BatchProcessingService
    ↓
    ├── File Validation (validate_batch_files_optimized)
    ├── Resource Allocation (get_optimal_batch_size)
    ├── Parallel Processing (process_in_parallel)
    └── Result Aggregation
   ```

## GDPR Compliance Features

1. **Data Minimization**: Only necessary data is processed and stored
    - Controlled by `DATA_MINIMIZATION_RULES` in `gdpr_config.py`

2. **Processing Records**: Maintains GDPR-compliant audit trails
    - Records stored in `app/logs/processing_records/`
    - Retention period: 90 days (configurable)

3. **Temporary File Management**: Ensures files are properly deleted
    - `TEMP_FILE_RETENTION_SECONDS`: 3600 (1 hour)
    - `REDACTED_FILE_RETENTION_SECONDS`: 86400 (24 hours)

4. **Secure Error Handling**: Prevents leakage of sensitive information
    - Sanitizes error messages
    - Records detailed errors securely

## API Rate Limiting

Rate limiting is controlled via environment variables:

- `RATE_LIMIT_RPM`: 60 (standard users)
- `ADMIN_RATE_LIMIT_RPM`: 120 (admin users)
- `ANON_RATE_LIMIT_RPM`: 30 (anonymous users)
- `RATE_LIMIT_BURST`: 10 (short burst allowance)

Redis can be used for distributed rate limiting by setting `REDIS_URL`.


### PDF Redaction

#### Request:

```bash
# Redact sensitive information in a PDF
curl -X POST http://localhost:8000/pdf/redact \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf" \
  -F 'redaction_mapping={"pages":[{"page":1,"sensitive":[{"entity_type":"PERSON","text":"John Doe","positions":[[100,108]],"confidence":0.92,"boxes":[[100,180,200,200]]}]}]}' \
  --output redacted.pdf
```

#### Response:

The redacted PDF file with the following headers:

- `Content-Disposition`: "attachment; filename=redacted.pdf"
- `X-Redaction-Time`: "0.453s"
- `X-Total-Time`: "0.562s"
- `X-Redactions-Applied`: "1"
- `X-Memory-Usage`: "45.3%"
- `X-Peak-Memory`: "67.8%"
- `X-Operation-ID`: "pdf_redact_1709372851"

### Batch Processing

#### Request:

```bash
# Process multiple files in batch mode
curl -X POST http://localhost:8000/batch/detect \
  -H "Content-Type: multipart/form-data" \
  -F "files=@document1.pdf" \
  -F "files=@document2.pdf" \
  -F "files=@document3.pdf" \
  -F "requested_entities=PERSON,EMAIL_ADDRESS" \
  -F "detection_engine=presidio" \
  -F "max_parallel_files=3"
```

#### Response:

``` json
{
  "batch_summary": {
    "total_files": 3,
    "successful": 3,
    "failed": 0,
    "total_time": 2.567,
    "workers": 3,
    "operation_id": "batch_detect_1709372851",
    "lock_used": true
  },
  "file_results": [
      "file": "Inspeksjonsrapport-2.pdf",
            "status": "success",
            "results": {
                "redaction_mapping": {
                    "pages": [
                        {
                            "page": 1,
                            "sensitive": [
                                {
                                    "original_text": "Astrid Holm",
                                    "entity_type": "PERSON",
                                    "start": 15,
                                    "end": 26,
                                    "score": 0.9846669435501099,
                                    "bbox": {
                                        "x0": 147.44161987304688,
                                        "y0": 72.75343322753906,
                                        "x1": 203.49172973632812,
                                        "y1": 82.2332763671875
                                    }
                                },
                                {
                                    "original_text": "Astrid Holm",
                                    "entity_type": "PERSON",
                                    "start": 314,
                                    "end": 325,
                                    "score": 0.9846669435501099,
                                    "bbox": {
                                        "x0": 147.32015991210938,
                                        "y0": 146.8134307861328,
                                        "x1": 203.3813018798828,
                                        "y1": 156.29327392578125
                                    }
                                },
                                {
                                    "original_text": "Førsteinspektør Eva Hansen",
                                    "entity_type": "PERSON",
                                    "start": 268,
                                    "end": 294,
                                    "score": 0.8434117436408997,
                                    "bbox": {
                                        "x0": 360.4693603515625,
                                        "y0": 132.2934112548828,
                                        "x1": 493.5455627441406,
                                        "y1": 141.77325439453125
                                    }
                                },
        "entities_detected": {
                    "total": 12,
                    "by_type": {
                        "PERSON": 12
                    },
                    "by_page": {
                        "page_1": 4,
                        "page_2": 11,
                        "page_3": 1
                    }
                },
                "performance": {
                    "words_count": 745,
                    "pages_count": 3,
                    "entity_density": 16.107382550335572,
                    "sanitize_time": 0.002001047134399414
                },
                "file_info": {
                    "filename": "Inspeksjonsrapport-2.pdf",
                    "content_type": "application/pdf",
                    "size": "0.06 MB"
                },
                "model_info": {
                    "engine": "GLINER"
                }
            }
        },
    {
            "file": "Inspeksjonsrapport-3.pdf",
            "status": "success",
            "results": {
                "redaction_mapping": {
                    "pages": [
                        {
                            "page": 1,
                            "sensitive": [ {/* Redaction mapping for document2.pdf */},
                            .
                            .
                            .
                        }
                    ]
                },
              "entities_detected": {
                    "total": 11,
                    "by_type": {
                        "PERSON": 11
                    },
                    "by_page": {
                        "page_1": 7,
                        "page_2": 5,
                        "page_3": 1
                    }
                },
                "performance": {
                    "words_count": 475,
                    "pages_count": 3,
                    "entity_density": 23.157894736842106,
                    "sanitize_time": 0.0010004043579101562
                },
                "file_info": {
                    "filename": "Inspeksjonsrapport-3.pdf",
                    "content_type": "application/pdf",
                    "size": "0.07 MB"
                },
                "model_info": {
                    "engine": "GLINER"
                }
              }
              
            }
    }
 ]      
}
```

### Getting Available Entity Types

#### Request:

```bash
# Get all available entity types
curl -X GET http://localhost:8000/help/entities
```

#### Response:

```json
{
  "presidio_entities": [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "ADDRESS",
    "DATE",
    "US_SSN",
    "LOCATION",
    "ORGANIZATION",
    "NO_FODSELSNUMMER",
    "NO_PHONE_NUMBER"
  ],
  "gemini_entities": {
    "PERSON": "Names of individuals",
    "EMAIL_ADDRESS": "Email addresses",
    "PHONE_NUMBER": "Phone and fax numbers",
    "CREDIT_CARD": "Credit card numbers",
    "ADDRESS": "Physical addresses",
    "DATE": "Dates in various formats",
    "US_SSN": "US Social Security Numbers",
    "LOCATION": "Geographic locations",
    "ORGANIZATION": "Names of companies and organizations"
  },
  "gliner_entities": [
    "PERSON",
    "EMAIL",
    "PHONE",
    "ADDRESS",
    "ID_NUMBER",
    "CREDIT_CARD",
    "MEDICAL_RECORD",
    "BANK_ACCOUNT",
    "AGE"
  ]
}
```

## Error Handling

All API endpoints implement consistent error handling with security-aware responses to prevent information leakage:

### Rate Limit Exceeded

```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds.",
  "retry_after": 60
}
```

### File Size Exceeded

```json
{
  "detail": "PDF file size exceeds maximum allowed (25MB)"
}
```

### Invalid File Format

```json
{
  "detail": "Unsupported file type. Please upload a PDF or text file."
}
```

### Service Overload

```json
{
  "detail": "Service unable to process batch due to system load.",
  "retry_after": 60,
  "operation_id": "batch_detect_1709372851"
}
```

## Monitoring and Maintenance

### Key Metrics to Monitor

1. **Memory Usage**: `memory_monitor.get_memory_stats()`
    - Watch for consistently high memory usage (>90%)
    - Monitor peak memory usage patterns

2. **Processing Times**:
    - Entity detection time by engine type
    - Redaction time by document size
    - Total processing time per document

3. **Error Rates**:
    - Monitor `/app/logs/error_logs/detailed_errors.log`
    - Track rate limiting rejections

### Maintenance Tasks

1. **Regular GDPR Cleanup**:
    - Ensure `retention_manager` is properly running
    - Verify processing records rotation (90 days default)

2. **GLiNER Model Updates**:
    - Check for newer model versions periodically
    - Clear model cache when updating

3. **Log Rotation**:
    - Set up log rotation for error logs and processing records
    - Recommended: Daily rotation with 30-day retention

## Extending the System

### Adding New Document Types

To add support for a new document format:

1. Create a new extractor class implementing `DocumentExtractor` interface
2. Create a new redactor class implementing `DocumentRedactor` interface
3. Add format to `DocumentFormat` enum in `document_processing_factory.py`
4. Update the factory methods to handle the new format

### Adding New Detection Engines

To integrate a new entity detection engine:

1. Create a new detector class extending `BaseEntityDetector`
2. Implement `detect_sensitive_data_async()` and other required methods
3. Add the engine to `EntityDetectionEngine` enum in `document_processing_factory.py`
4. Update the `InitializationService` to handle the new engine

### Custom Entity Detection Rules

For domain-specific entity detection:

1. Add custom regex patterns to `recognizers-config.yml`
2. Create a custom Presidio analyzer configuration
3. Integrate domain-specific keywords and patterns

## Copyright and License

© 2025 HideMeAI. All Rights Reserved.

This software is proprietary and confidential. Unauthorized copying, transfer, or use of this software, its
documentation, or any related materials, via any medium, is strictly prohibited without prior written permission from
HideMeAI.

This software contains trade secrets and confidential information of HideMeAI. Distribution of modified versions of this
software is prohibited unless explicitly authorized by HideMeAI.

For licensing inquiries, please contact: licensing@hidemeai.com
   