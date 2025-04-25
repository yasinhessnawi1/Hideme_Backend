package constants

// Table Names
const (
	TableUsers            = "users"
	TableUserSettings     = "user_settings"
	TableDocuments        = "documents"
	TableDetectionMethods = "detection_methods"
	TableDetectedEntities = "detected_entities"
	TableModelEntities    = "model_entities"
	TableSearchPatterns   = "search_patterns"
	TableBanLists         = "ban_lists"
	TableBanListWords     = "ban_list_words"
	TableSessions         = "sessions"
	TableAPIKeys          = "api_keys"
	TableMigrations       = "migrations"
	TableSeeds            = "seeds"
)

// Common Column Names
const (
	ColumnID             = "id"
	ColumnUserID         = "user_id"
	ColumnSettingID      = "setting_id"
	ColumnBanID          = "ban_id"
	ColumnMethodID       = "method_id"
	ColumnEntityID       = "entity_id"
	ColumnPatternID      = "pattern_id"
	ColumnCreatedAt      = "created_at"
	ColumnUpdatedAt      = "updated_at"
	ColumnUsername       = "username"
	ColumnEmail          = "email"
	ColumnPasswordHash   = "password_hash"
	ColumnSalt           = "salt"
	ColumnKeyID          = "key_id"
	ColumnAPIKeyHash     = "api_key_hash"
	ColumnName           = "name"
	ColumnExpiresAt      = "expires_at"
	ColumnWord           = "word"
	ColumnPatternType    = "pattern_type"
	ColumnPatternText    = "pattern_text"
	ColumnSessionID      = "session_id"
	ColumnJWTID          = "jwt_id"
	ColumnDocumentID     = "document_id"
	ColumnEntityName     = "entity_name"
	ColumnEntityText     = "entity_text"
	ColumnMethodName     = "method_name"
	ColumnHighlightColor = "highlight_color"
)

// Index Names
const (
	IndexUserID     = "idx_user_id"
	IndexSettingID  = "idx_setting_id"
	IndexMethodID   = "idx_method_id"
	IndexEntityName = "idx_entity_name"
	IndexBanID      = "idx_ban_id"
	IndexWord       = "idx_word"
	IndexUsername   = "idx_username"
	IndexEmail      = "idx_email"
	IndexJWTID      = "idx_jwt_id"
	IndexExpiresAt  = "idx_expires_at"
	IndexBanWord    = "idx_ban_word"
)

// Database Schema Names
const (
	SchemaInformation = "information_schema"
	SchemaPublic      = "public"
	CurrentSchema     = "current_schema()"
)

// Database Query Templates
const (
	QueryCheckTableExists  = "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = current_schema() AND table_name = $1)"
	QueryCheckColumnExists = "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name = $1 AND column_name = $2)"
)
