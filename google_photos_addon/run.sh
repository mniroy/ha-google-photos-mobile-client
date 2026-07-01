#!/usr/bin/with-contenv bashio

AUTH_DATA=$(bashio::config 'auth_data')
PATH_TO_UPLOAD=$(bashio::config 'path')
ALBUM=$(bashio::config 'album')
LOG_LEVEL=$(bashio::config 'log_level')
BATCH_SIZE=$(bashio::config 'batch_size')

ARGS=()

if bashio::config.has_value 'album'; then
    ARGS+=("--album" "$ALBUM")
fi

if bashio::config.true 'recursive'; then
    ARGS+=("--recursive")
fi

if bashio::config.true 'delete_from_host'; then
    ARGS+=("--delete-from-host")
fi

if bashio::config.has_value 'log_level'; then
    ARGS+=("--log-level" "$LOG_LEVEL")
fi

if bashio::config.has_value 'batch_size'; then
    ARGS+=("--batch-size" "$BATCH_SIZE")
fi

bashio::log.info "Start Google Photos upload..."
export GP_AUTH_DATA="$AUTH_DATA"

gpmc "$PATH_TO_UPLOAD" "${ARGS[@]}"
