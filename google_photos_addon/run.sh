#!/usr/bin/with-contenv bashio

AUTH_DATA=$(bashio::config 'auth_data')
PATH_TO_UPLOAD=$(bashio::config 'path')

ARGS=()

if bashio::config.has_value 'album'; then
    ARGS+=("--album" "$(bashio::config 'album')")
fi

if bashio::config.true 'recursive'; then
    ARGS+=("--recursive")
fi

if bashio::config.true 'delete_from_host'; then
    ARGS+=("--delete-from-host")
fi

if bashio::config.has_value 'log_level'; then
    ARGS+=("--log-level" "$(bashio::config 'log_level')")
fi

if bashio::config.has_value 'batch_size'; then
    ARGS+=("--batch-size" "$(bashio::config 'batch_size')")
fi

bashio::log.info "Start Google Photos upload..."
export GP_AUTH_DATA="$AUTH_DATA"

gpmc "$PATH_TO_UPLOAD" "${ARGS[@]}"
