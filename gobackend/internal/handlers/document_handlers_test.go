package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/service"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// MockDocumentService is a mock implementation of DocumentServiceInterface
type MockDocumentService struct {
	mock.Mock
}

func (m *MockDocumentService) ListDocuments(userID int64, page, pageSize int) ([]*models.Document, int, error) {
	args := m.Called(userID, page, pageSize)
	if args.Get(0) == nil {
		return nil, args.Int(1), args.Error(2)
	}
	return args.Get(0).([]*models.Document), args.Int(1), args.Error(2)
}

func (m *MockDocumentService) UploadDocument(userID int64, filename string, redactionSchema models.RedactionMapping) (*models.Document, error) {
	args := m.Called(userID, filename, redactionSchema)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.Document), args.Error(1)
}

func (m *MockDocumentService) GetDocumentByID(id int64) (*models.Document, error) {
	args := m.Called(id)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.Document), args.Error(1)
}

func (m *MockDocumentService) DeleteDocumentByID(id int64) error {
	args := m.Called(id)
	return args.Error(0)
}

func (m *MockDocumentService) GetDocumentSummary(id int64) (*models.DocumentSummary, error) {
	args := m.Called(id)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.DocumentSummary), args.Error(1)
}

func (m *MockDocumentService) CalculateEntityCount(redactionSchema string) int {
	args := m.Called(redactionSchema)
	return args.Int(0)
}

// Test helpers
func setupDocumentTest(t *testing.T) (*DocumentHandler, *MockDocumentService) {
	mockService := new(MockDocumentService)
	handler := NewDocumentHandler(mockService)
	return handler, mockService
}

func createDocumentAuthContext(userID int64) context.Context {
	ctx := context.Background()
	ctx = context.WithValue(ctx, auth.ContextKey("user_id"), userID)
	return ctx
}

// Test cases
func TestNewDocumentHandler(t *testing.T) {
	// Test that the constructor properly initializes the handler
	mockService := new(MockDocumentService)
	handler := NewDocumentHandler(mockService)

	assert.NotNil(t, handler)
	assert.Equal(t, mockService, handler.documentService)
}

// ListDocuments tests
func TestListDocuments(t *testing.T) {
	t.Run("Successful listing", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		req := httptest.NewRequest(http.MethodGet, "/api/documents?page=1&page_size=10", nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		rr := httptest.NewRecorder()

		// Create test documents
		testTime := time.Now()
		mockDocs := []*models.Document{
			{
				ID:                 1,
				UserID:             userID,
				HashedDocumentName: "test-doc-1",
				UploadTimestamp:    testTime,
				LastModified:       testTime,
				RedactionSchema:    "schema1",
			},
			{
				ID:                 2,
				UserID:             userID,
				HashedDocumentName: "test-doc-2",
				UploadTimestamp:    testTime,
				LastModified:       testTime,
				RedactionSchema:    "schema2",
			},
		}

		totalDocs := 2

		mockService.On("ListDocuments", userID, 1, 10).Return(mockDocs, totalDocs, nil)
		mockService.On("CalculateEntityCount", "schema1").Return(5)
		mockService.On("CalculateEntityCount", "schema2").Return(3)

		// Act
		handler.ListDocuments(rr, req)

		// Assert
		assert.Equal(t, http.StatusOK, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		// Check response structure
		assert.True(t, response.Success)
		assert.NotNil(t, response.Data)
		assert.NotNil(t, response.Meta)
		assert.Equal(t, 1, response.Meta.Page)
		assert.Equal(t, 10, response.Meta.PageSize)
		assert.Equal(t, totalDocs, response.Meta.TotalItems)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Unauthorized access", func(t *testing.T) {
		// Arrange
		handler, _ := setupDocumentTest(t)

		req := httptest.NewRequest(http.MethodGet, "/api/documents", nil)
		// No user ID in context

		rr := httptest.NewRecorder()

		// Act
		handler.ListDocuments(rr, req)

		// Assert
		assert.Equal(t, http.StatusUnauthorized, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		assert.False(t, response.Success)
		assert.Equal(t, constants.MsgAuthRequired, response.Error.Message)
	})

	t.Run("Service error", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		req := httptest.NewRequest(http.MethodGet, "/api/documents?page=1&page_size=10", nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		rr := httptest.NewRecorder()

		serviceErr := errors.New("database error")
		mockService.On("ListDocuments", userID, 1, 10).Return(nil, 0, serviceErr)

		// Act
		handler.ListDocuments(rr, req)

		// Assert
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		assert.False(t, response.Success)
		assert.NotNil(t, response.Error)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})
}

// UploadDocument tests
func TestUploadDocument(t *testing.T) {
	t.Run("Successful upload", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)

		redactionMapping := models.RedactionMapping{
			Pages: []models.Page{
				{
					PageNumber: 1,
					Sensitive: []models.Sensitive{
						{
							OriginalText: "test",
							EntityType:   "PII",
							Score:        0.9,
							Start:        1,
							End:          4,
							BBox: models.BBox{
								X0: 1.0,
								Y0: 1.0,
								X1: 2.0,
								Y1: 2.0,
							},
						},
					},
				},
			},
		}

		requestBody := struct {
			Filename        string                  `json:"filename"`
			RedactionSchema models.RedactionMapping `json:"redaction_schema"`
		}{
			Filename:        "sensitive-document.pdf",
			RedactionSchema: redactionMapping,
		}

		jsonBody, _ := json.Marshal(requestBody)

		req := httptest.NewRequest(http.MethodPost, "/api/documents", bytes.NewBuffer(jsonBody))
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createDocumentAuthContext(userID))

		rr := httptest.NewRecorder()

		testTime := time.Now()
		mockDoc := &models.Document{
			ID:                 1,
			UserID:             userID,
			HashedDocumentName: "sensitive-document.pdf",
			UploadTimestamp:    testTime,
			LastModified:       testTime,
		}

		mockService.On("UploadDocument", userID, "sensitive-document.pdf", redactionMapping).Return(mockDoc, nil)

		// Act
		handler.UploadDocument(rr, req)

		// Assert
		assert.Equal(t, constants.StatusCreated, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		assert.True(t, response.Success)
		assert.NotNil(t, response.Data)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid JSON", func(t *testing.T) {
		// Arrange
		handler, _ := setupDocumentTest(t)

		userID := int64(123)

		invalidJSON := `{"filename": "test", "redaction_schema": invalid}`
		req := httptest.NewRequest(http.MethodPost, "/api/documents", bytes.NewBufferString(invalidJSON))
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createDocumentAuthContext(userID))

		rr := httptest.NewRecorder()

		// Act
		handler.UploadDocument(rr, req)

		// Assert
		assert.Equal(t, http.StatusBadRequest, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		assert.False(t, response.Success)
		assert.Equal(t, "Invalid request data required filename and redaction schema", response.Error.Message)
	})

	t.Run("Missing filename", func(t *testing.T) {
		// Arrange
		handler, _ := setupDocumentTest(t)

		userID := int64(123)

		redactionMapping := models.RedactionMapping{
			Pages: []models.Page{
				{
					PageNumber: 1,
					Sensitive:  []models.Sensitive{},
				},
			},
		}

		requestBody := struct {
			Filename        string                  `json:"filename"`
			RedactionSchema models.RedactionMapping `json:"redaction_schema"`
		}{
			Filename:        "", // Empty filename
			RedactionSchema: redactionMapping,
		}

		jsonBody, _ := json.Marshal(requestBody)

		req := httptest.NewRequest(http.MethodPost, "/api/documents", bytes.NewBuffer(jsonBody))
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createDocumentAuthContext(userID))

		rr := httptest.NewRecorder()

		// Act
		handler.UploadDocument(rr, req)

		// Assert
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Service error", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)

		redactionMapping := models.RedactionMapping{
			Pages: []models.Page{
				{
					PageNumber: 1,
					Sensitive:  []models.Sensitive{},
				},
			},
		}

		requestBody := struct {
			Filename        string                  `json:"filename"`
			RedactionSchema models.RedactionMapping `json:"redaction_schema"`
		}{
			Filename:        "test-document.pdf",
			RedactionSchema: redactionMapping,
		}

		jsonBody, _ := json.Marshal(requestBody)

		req := httptest.NewRequest(http.MethodPost, "/api/documents", bytes.NewBuffer(jsonBody))
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createDocumentAuthContext(userID))

		rr := httptest.NewRecorder()

		serviceErr := errors.New("storage error")
		mockService.On("UploadDocument", userID, "test-document.pdf", redactionMapping).Return(nil, serviceErr)

		// Act
		handler.UploadDocument(rr, req)

		// Assert
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid document ID error", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)

		redactionMapping := models.RedactionMapping{
			Pages: []models.Page{
				{
					PageNumber: 1,
					Sensitive:  []models.Sensitive{},
				},
			},
		}

		requestBody := struct {
			Filename        string                  `json:"filename"`
			RedactionSchema models.RedactionMapping `json:"redaction_schema"`
		}{
			Filename:        "test-document.pdf",
			RedactionSchema: redactionMapping,
		}

		jsonBody, _ := json.Marshal(requestBody)

		req := httptest.NewRequest(http.MethodPost, "/api/documents", bytes.NewBuffer(jsonBody))
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createDocumentAuthContext(userID))

		rr := httptest.NewRecorder()

		mockService.On("UploadDocument", userID, "test-document.pdf", redactionMapping).Return(nil, service.ErrInvalidDocumentID)

		// Act
		handler.UploadDocument(rr, req)

		// Assert
		assert.Equal(t, http.StatusBadRequest, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		assert.False(t, response.Success)
		assert.Equal(t, "Invalid document ID", response.Error.Message)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})
}

// GetDocumentByID tests
func TestGetDocumentByID(t *testing.T) {
	// Setup a router for URL parameter extraction
	setupChiRouter := func(handler http.HandlerFunc) (http.Handler, *httptest.ResponseRecorder) {
		r := chi.NewRouter()
		r.Get("/api/documents/{id}", handler)
		rr := httptest.NewRecorder()
		return r, rr
	}

	t.Run("Successful retrieval", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		docID := int64(456)

		router, rr := setupChiRouter(handler.GetDocumentByID)

		req := httptest.NewRequest(http.MethodGet, "/api/documents/"+strconv.FormatInt(docID, 10), nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		testTime := time.Now()
		mockDoc := &models.Document{
			ID:                 docID,
			UserID:             userID,
			HashedDocumentName: "test-document.pdf",
			UploadTimestamp:    testTime,
			LastModified:       testTime,
			RedactionSchema:    "schema1",
		}

		mockService.On("GetDocumentByID", docID).Return(mockDoc, nil)

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusOK, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		assert.True(t, response.Success)
		assert.NotNil(t, response.Data)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid document ID parameter", func(t *testing.T) {
		// Arrange
		handler, _ := setupDocumentTest(t)

		userID := int64(123)

		router, rr := setupChiRouter(handler.GetDocumentByID)

		req := httptest.NewRequest(http.MethodGet, "/api/documents/invalid", nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusBadRequest, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		assert.False(t, response.Success)
		assert.Equal(t, "Invalid document ID", response.Error.Message)
	})

	t.Run("Document not found", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		docID := int64(999)

		router, rr := setupChiRouter(handler.GetDocumentByID)

		req := httptest.NewRequest(http.MethodGet, "/api/documents/"+strconv.FormatInt(docID, 10), nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		mockService.On("GetDocumentByID", docID).Return(nil, service.ErrDocumentNotFound)

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusNotFound, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		assert.False(t, response.Success)
		assert.Equal(t, "Document not found", response.Error.Message)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Service error", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		docID := int64(456)

		router, rr := setupChiRouter(handler.GetDocumentByID)

		req := httptest.NewRequest(http.MethodGet, "/api/documents/"+strconv.FormatInt(docID, 10), nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		serviceErr := errors.New("database error")
		mockService.On("GetDocumentByID", docID).Return(nil, serviceErr)

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Unauthorized access", func(t *testing.T) {
		// Arrange
		handler, _ := setupDocumentTest(t)

		docID := int64(456)

		router, rr := setupChiRouter(handler.GetDocumentByID)

		req := httptest.NewRequest(http.MethodGet, "/api/documents/"+strconv.FormatInt(docID, 10), nil)
		// No user ID in context

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})
}

// DeleteDocumentByID tests
func TestDeleteDocumentByID(t *testing.T) {
	// Setup a router for URL parameter extraction
	setupChiRouter := func(handler http.HandlerFunc) (http.Handler, *httptest.ResponseRecorder) {
		r := chi.NewRouter()
		r.Delete("/api/documents/{id}", handler)
		rr := httptest.NewRecorder()
		return r, rr
	}

	t.Run("Successful deletion", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		docID := int64(456)

		router, rr := setupChiRouter(handler.DeleteDocumentByID)

		req := httptest.NewRequest(http.MethodDelete, "/api/documents/"+strconv.FormatInt(docID, 10), nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		mockService.On("DeleteDocumentByID", docID).Return(nil)

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusNoContent, rr.Code)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid document ID parameter", func(t *testing.T) {
		// Arrange
		handler, _ := setupDocumentTest(t)

		userID := int64(123)

		router, rr := setupChiRouter(handler.DeleteDocumentByID)

		req := httptest.NewRequest(http.MethodDelete, "/api/documents/invalid", nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Document not found", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		docID := int64(999)

		router, rr := setupChiRouter(handler.DeleteDocumentByID)

		req := httptest.NewRequest(http.MethodDelete, "/api/documents/"+strconv.FormatInt(docID, 10), nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		mockService.On("DeleteDocumentByID", docID).Return(service.ErrDocumentNotFound)

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusNotFound, rr.Code)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Service error", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		docID := int64(456)

		router, rr := setupChiRouter(handler.DeleteDocumentByID)

		req := httptest.NewRequest(http.MethodDelete, "/api/documents/"+strconv.FormatInt(docID, 10), nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		serviceErr := errors.New("database error")
		mockService.On("DeleteDocumentByID", docID).Return(serviceErr)

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Unauthorized access", func(t *testing.T) {
		// Arrange
		handler, _ := setupDocumentTest(t)

		docID := int64(456)

		router, rr := setupChiRouter(handler.DeleteDocumentByID)

		req := httptest.NewRequest(http.MethodDelete, "/api/documents/"+strconv.FormatInt(docID, 10), nil)
		// No user ID in context

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})
}

// GetDocumentSummary tests
func TestGetDocumentSummary(t *testing.T) {
	// Setup a router for URL parameter extraction
	setupChiRouter := func(handler http.HandlerFunc) (http.Handler, *httptest.ResponseRecorder) {
		r := chi.NewRouter()
		r.Get("/api/documents/{id}/summary", handler)
		rr := httptest.NewRecorder()
		return r, rr
	}

	t.Run("Successful retrieval", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		docID := int64(456)

		router, rr := setupChiRouter(handler.GetDocumentSummary)

		req := httptest.NewRequest(http.MethodGet, "/api/documents/"+strconv.FormatInt(docID, 10)+"/summary", nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		testTime := time.Now()
		mockSummary := &models.DocumentSummary{
			ID:              docID,
			HashedName:      "test-document.pdf",
			UploadTimestamp: testTime,
			LastModified:    testTime,
			EntityCount:     5,
		}

		mockService.On("GetDocumentSummary", docID).Return(mockSummary, nil)

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusOK, rr.Code)

		var response utils.Response
		err := json.Unmarshal(rr.Body.Bytes(), &response)
		assert.NoError(t, err)

		assert.True(t, response.Success)
		assert.NotNil(t, response.Data)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid document ID parameter", func(t *testing.T) {
		// Arrange
		handler, _ := setupDocumentTest(t)

		userID := int64(123)

		router, rr := setupChiRouter(handler.GetDocumentSummary)

		req := httptest.NewRequest(http.MethodGet, "/api/documents/invalid/summary", nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Service error", func(t *testing.T) {
		// Arrange
		handler, mockService := setupDocumentTest(t)

		userID := int64(123)
		docID := int64(456)

		router, rr := setupChiRouter(handler.GetDocumentSummary)

		req := httptest.NewRequest(http.MethodGet, "/api/documents/"+strconv.FormatInt(docID, 10)+"/summary", nil)
		req = req.WithContext(createDocumentAuthContext(userID))

		serviceErr := errors.New("database error")
		mockService.On("GetDocumentSummary", docID).Return(nil, serviceErr)

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify the mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Unauthorized access", func(t *testing.T) {
		// Arrange
		handler, _ := setupDocumentTest(t)

		docID := int64(456)

		router, rr := setupChiRouter(handler.GetDocumentSummary)

		req := httptest.NewRequest(http.MethodGet, "/api/documents/"+strconv.FormatInt(docID, 10)+"/summary", nil)
		// No user ID in context

		// Act
		router.ServeHTTP(rr, req)

		// Assert
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})
}
