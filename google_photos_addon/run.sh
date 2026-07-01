#!/usr/bin/with-contenv bashio
set -x

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
    VAL=$(bashio::config 'log_level')
    if [[ "$VAL" == *"["* ]]; then
        VAL=$(bashio::jq "${__BASHIO_ADDON_OPTIONS}" ".log_level[0]")
    fi
    ARGS+=("--log-level" "$VAL")
fi

if bashio::config.has_value 'batch_size'; then
    VAL=$(bashio::config 'batch_size')
    if [[ "$VAL" == *"["* ]]; then
        VAL=$(bashio::jq "${__BASHIO_ADDON_OPTIONS}" ".batch_size[0]")
    fi
    ARGS+=("--batch-size" "$VAL")
fi

bashio::log.info "Start Google Photos upload..."
export GP_AUTH_DATA="$AUTH_DATA"

gpmc "$PATH_TO_UPLOAD" "${ARGS[@]}"
