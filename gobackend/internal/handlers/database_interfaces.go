package handlers

import (
	"context"
)

// DatabaseServiceInterface defines methods required from DatabaseService
type DatabaseServiceInterface interface {
	ValidateTableAccess(table string) error
	ExecuteQuery(ctx context.Context, query string, params []interface{}, userID int64) ([]map[string]interface{}, error)
	GetTableData(ctx context.Context, table string, conditions map[string]interface{}) ([]map[string]interface{}, error)
	GetRecordByID(ctx context.Context, table string, id interface{}) (map[string]interface{}, error)
	CountTableRecords(ctx context.Context, table string, conditions map[string]interface{}) (int64, error)
	GetTableSchema(ctx context.Context, table string) ([]map[string]interface{}, error)
}
