package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// ModelEntityRepository defines methods for interacting with model entities
type ModelEntityRepository interface {
	Create(ctx context.Context, entity *models.ModelEntity) error
	CreateBatch(ctx context.Context, entities []*models.ModelEntity) error
	GetByID(ctx context.Context, id int64) (*models.ModelEntity, error)
	GetBySettingID(ctx context.Context, settingID int64) ([]*models.ModelEntity, error)
	GetBySettingIDAndMethodID(ctx context.Context, settingID, methodID int64) ([]*models.ModelEntityWithMethod, error)
	Update(ctx context.Context, entity *models.ModelEntity) error
	Delete(ctx context.Context, id int64) error
	DeleteBySettingID(ctx context.Context, settingID int64) error
	DeleteByMethodID(ctx context.Context, settingID, methodID int64) error
}

// PostgresModelEntityRepository is a PostgreSQL implementation of ModelEntityRepository
type PostgresModelEntityRepository struct {
	db *database.Pool
}

// NewModelEntityRepository creates a new ModelEntityRepository
func NewModelEntityRepository(db *database.Pool) ModelEntityRepository {
	return &PostgresModelEntityRepository{
		db: db,
	}
}

// Create adds a new model entity to the database
func (r *PostgresModelEntityRepository) Create(ctx context.Context, entity *models.ModelEntity) error {
	// Start query timer
	startTime := time.Now()

	// Define the query with RETURNING for PostgreSQL
	query := `
        INSERT INTO model_entities (setting_id, method_id, entity_text)
        VALUES ($1, $2, $3)
        RETURNING model_entity_id
    `

	// Execute the query
	err := r.db.QueryRowContext(
		ctx,
		query,
		entity.SettingID,
		entity.MethodID,
		entity.EntityText,
	).Scan(&entity.ID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{entity.SettingID, entity.MethodID, entity.EntityText},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to create model entity: %w", err)
	}

	log.Info().
		Int64("model_entity_id", entity.ID).
		Int64("setting_id", entity.SettingID).
		Int64("method_id", entity.MethodID).
		Msg("Model entity created")

	return nil
}

// CreateBatch adds multiple model entities to the database in a single transaction
func (r *PostgresModelEntityRepository) CreateBatch(ctx context.Context, entities []*models.ModelEntity) error {
	if len(entities) == 0 {
		return nil
	}

	// Start query timer
	startTime := time.Now()

	// Execute within a transaction
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// Define the query with RETURNING for PostgreSQL
		query := `
            INSERT INTO model_entities (setting_id, method_id, entity_text)
            VALUES ($1, $2, $3)
            RETURNING model_entity_id
        `

		// Add each entity individually
		for _, entity := range entities {
			var entityID int64
			err := tx.QueryRowContext(ctx, query, entity.SettingID, entity.MethodID, entity.EntityText).Scan(&entityID)
			if err != nil {
				return fmt.Errorf("failed to create model entity: %w", err)
			}

			// Set the entity ID
			entity.ID = entityID
		}

		// Log the operation
		utils.LogDBQuery(
			fmt.Sprintf("Created %d model entities", len(entities)),
			[]interface{}{entities[0].SettingID, entities[0].MethodID},
			time.Since(startTime),
			nil,
		)

		log.Info().
			Int("entity_count", len(entities)).
			Int64("setting_id", entities[0].SettingID).
			Int64("method_id", entities[0].MethodID).
			Msg("Model entities created in batch")

		return nil
	})
}

// GetByID retrieves a model entity by ID
func (r *PostgresModelEntityRepository) GetByID(ctx context.Context, id int64) (*models.ModelEntity, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT model_entity_id, setting_id, method_id, entity_text
        FROM model_entities
        WHERE model_entity_id = $1
    `

	// Execute the query
	entity := &models.ModelEntity{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&entity.ID,
		&entity.SettingID,
		&entity.MethodID,
		&entity.EntityText,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{id},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("ModelEntity", id)
		}
		return nil, fmt.Errorf("failed to get model entity by ID: %w", err)
	}

	return entity, nil
}

// GetBySettingID retrieves all model entities for a setting
func (r *PostgresModelEntityRepository) GetBySettingID(ctx context.Context, settingID int64) ([]*models.ModelEntity, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT model_entity_id, setting_id, method_id, entity_text
        FROM model_entities
        WHERE setting_id = $1
        ORDER BY method_id, entity_text
    `

	// Execute the query
	rows, err := r.db.QueryContext(ctx, query, settingID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settingID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get model entities by setting ID: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Parse the results
	var entities []*models.ModelEntity
	for rows.Next() {
		entity := &models.ModelEntity{}
		if err := rows.Scan(
			&entity.ID,
			&entity.SettingID,
			&entity.MethodID,
			&entity.EntityText,
		); err != nil {
			return nil, fmt.Errorf("failed to scan model entity row: %w", err)
		}
		entities = append(entities, entity)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating model entity rows: %w", err)
	}

	return entities, nil
}

// GetBySettingIDAndMethodID retrieves all model entities for a setting and method with method information
func (r *PostgresModelEntityRepository) GetBySettingIDAndMethodID(ctx context.Context, settingID, methodID int64) ([]*models.ModelEntityWithMethod, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT me.model_entity_id, me.setting_id, me.method_id, me.entity_text, dm.method_name
        FROM model_entities me
        JOIN detection_methods dm ON me.method_id = dm.method_id
        WHERE me.setting_id = $1 AND me.method_id = $2
        ORDER BY me.entity_text
    `

	// Execute the query
	rows, err := r.db.QueryContext(ctx, query, settingID, methodID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settingID, methodID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get model entities by setting ID and method ID: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Parse the results
	var entities []*models.ModelEntityWithMethod
	for rows.Next() {
		entity := &models.ModelEntityWithMethod{
			ModelEntity: models.ModelEntity{},
		}
		if err := rows.Scan(
			&entity.ID,
			&entity.SettingID,
			&entity.MethodID,
			&entity.EntityText,
			&entity.MethodName,
		); err != nil {
			return nil, fmt.Errorf("failed to scan model entity row: %w", err)
		}
		entities = append(entities, entity)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating model entity rows: %w", err)
	}

	return entities, nil
}

// Update updates a model entity in the database
func (r *PostgresModelEntityRepository) Update(ctx context.Context, entity *models.ModelEntity) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        UPDATE model_entities
        SET entity_text = $1
        WHERE model_entity_id = $2
    `

	// Execute the query
	result, err := r.db.ExecContext(
		ctx,
		query,
		entity.EntityText,
		entity.ID,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{entity.EntityText, entity.ID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to update model entity: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("ModelEntity", entity.ID)
	}

	log.Info().
		Int64("model_entity_id", entity.ID).
		Msg("Model entity updated")

	return nil
}

// Delete removes a model entity from the database
func (r *PostgresModelEntityRepository) Delete(ctx context.Context, id int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM model_entities WHERE model_entity_id = $1`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, id)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{id},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete model entity: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("ModelEntity", id)
	}

	log.Info().
		Int64("model_entity_id", id).
		Msg("Model entity deleted")

	return nil
}

// DeleteBySettingID removes all model entities for a setting
func (r *PostgresModelEntityRepository) DeleteBySettingID(ctx context.Context, settingID int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM model_entities WHERE setting_id = $1`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, settingID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settingID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete model entities by setting ID: %w", err)
	}

	// Log the deletion
	rowsAffected, _ := result.RowsAffected()
	log.Info().
		Int64("setting_id", settingID).
		Int64("count", rowsAffected).
		Msg("Model entities deleted for setting")

	return nil
}

// DeleteByMethodID removes all model entities for a setting and method
func (r *PostgresModelEntityRepository) DeleteByMethodID(ctx context.Context, settingID, methodID int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM model_entities WHERE setting_id = $1 AND method_id = $2`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, settingID, methodID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settingID, methodID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete model entities by setting ID and method ID: %w", err)
	}

	// Log the deletion
	rowsAffected, _ := result.RowsAffected()
	log.Info().
		Int64("setting_id", settingID).
		Int64("method_id", methodID).
		Int64("count", rowsAffected).
		Msg("Model entities deleted for setting and method")

	return nil
}
