package handlers

import (
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog/log"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// DocumentServiceInterface defines the service methods required for document operations.
type DocumentServiceInterface interface {
	ListDocuments(userID int64, page, pageSize int) ([]*models.Document, int, error)
	UploadDocument(userID int64, filename string) (*models.Document, error)
	GetDocumentByID(id int64) (*models.Document, error)
	DeleteDocumentByID(id int64) error
	GetDocumentSummary(id int64) (*models.DocumentSummary, error)
}

// DocumentService implements DocumentServiceInterface using a DocumentRepository.
type DocumentService struct {
	docRepo repository.DocumentRepository
}

// DocumentHandler handles HTTP requests related to documents.
type DocumentHandler struct {
	documentService DocumentServiceInterface
}

// NewDocumentHandler creates a new DocumentHandler with the provided service.
func NewDocumentHandler(documentService DocumentServiceInterface) *DocumentHandler {
	return &DocumentHandler{documentService: documentService}
}

// ListDocuments handles GET /api/documents
func (h *DocumentHandler) ListDocuments(w http.ResponseWriter, r *http.Request) {
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}
	params := utils.GetPaginationParams(r)
	log.Info().Int64("user_id", userID).Int("page", params.Page).Int("page_size", params.PageSize).Msg("Listing documents")
	docs, total, err := h.documentService.ListDocuments(userID, params.Page, params.PageSize)
	if err != nil {
		log.Error().Err(err).Int64("user_id", userID).Msg("Failed to list documents")
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}
	utils.Paginated(w, constants.StatusOK, docs, params.Page, params.PageSize, total)
}

// UploadDocument handles POST /api/documents
func (h *DocumentHandler) UploadDocument(w http.ResponseWriter, r *http.Request) {
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}
	var req struct {
		Filename string `json:"filename" validate:"required"`
	}
	if err := utils.DecodeAndValidate(r, &req); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}
	log.Info().Int64("user_id", userID).Str("filename", req.Filename).Msg("Uploading document")
	doc, err := h.documentService.UploadDocument(userID, req.Filename)
	if err != nil {
		log.Error().Err(err).Int64("user_id", userID).Str("filename", req.Filename).Msg("Failed to upload document")
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}
	utils.JSON(w, constants.StatusCreated, doc)
}

// GetDocumentByID handles GET /api/documents/{id}
func (h *DocumentHandler) GetDocumentByID(w http.ResponseWriter, r *http.Request) {
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}
	idStr := chi.URLParam(r, "id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid document ID", nil)
		return
	}
	log.Info().Int64("user_id", userID).Int64("document_id", id).Msg("Getting document by ID")
	doc, err := h.documentService.GetDocumentByID(id)
	if err != nil {
		log.Error().Err(err).Int64("user_id", userID).Int64("document_id", id).Msg("Failed to get document by ID")
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}
	utils.JSON(w, constants.StatusOK, doc)
}

// DeleteDocumentByID handles DELETE /api/documents/{id}
func (h *DocumentHandler) DeleteDocumentByID(w http.ResponseWriter, r *http.Request) {
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}
	idStr := chi.URLParam(r, "id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid document ID", nil)
		return
	}
	log.Info().Int64("user_id", userID).Int64("document_id", id).Msg("Deleting document by ID")
	if err := h.documentService.DeleteDocumentByID(id); err != nil {
		log.Error().Err(err).Int64("user_id", userID).Int64("document_id", id).Msg("Failed to delete document by ID")
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}
	utils.NoContent(w)
}

// GetDocumentSummary handles GET /api/documents/{id}/summary
func (h *DocumentHandler) GetDocumentSummary(w http.ResponseWriter, r *http.Request) {
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}
	idStr := chi.URLParam(r, "id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid document ID", nil)
		return
	}
	log.Info().Int64("user_id", userID).Int64("document_id", id).Msg("Getting document summary")
	summary, err := h.documentService.GetDocumentSummary(id)
	if err != nil {
		log.Error().Err(err).Int64("user_id", userID).Int64("document_id", id).Msg("Failed to get document summary")
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}
	utils.JSON(w, constants.StatusOK, summary)
}
