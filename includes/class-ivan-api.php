<?php
/**
 * Ivan AI Chatbot API Adapter
 *
 * Handles public WordPress REST API endpoint `/wp-json/ivan/v1/chat`
 * Adapts widget requests to the Ivan FastAPI backend, preserves conversation state,
 * keeps backend API credentials secure server-side, and supports real-time SSE streaming.
 *
 * @package Ivan_AI_Chatbot
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit; // Exit if accessed directly.
}

class Ivan_API {

    /**
     * REST API Namespace.
     */
    const REST_NAMESPACE = 'ivan/v1';

    /**
     * REST API Route.
     */
    const REST_ROUTE = '/chat';

    /**
     * Rate limit: max requests per window.
     */
    const RATE_LIMIT_MAX = 30;

    /**
     * Rate limit: window in seconds.
     */
    const RATE_LIMIT_WINDOW = 60;

    /**
     * Backend HTTP timeout in seconds.
     */
    const BACKEND_TIMEOUT = 45;

    /**
     * Register REST API routes.
     */
    public function register_routes() {
        register_rest_route(
            self::REST_NAMESPACE,
            self::REST_ROUTE,
            array(
                'methods'             => WP_REST_Server::CREATABLE,
                'callback'            => array( $this, 'handle_chat_request' ),
                'permission_callback' => array( $this, 'check_permissions' ),
                'args'                => $this->get_endpoint_args(),
            )
        );
    }

    /**
     * Public access permission callback.
     *
     * @param WP_REST_Request $request Request object.
     * @return bool|WP_Error True if allowed, WP_Error otherwise.
     */
    public function check_permissions( $request ) {
        // Enforce rate limiting based on client IP
        $client_ip = $this->get_client_ip();
        if ( $this->is_rate_limited( $client_ip ) ) {
            return new WP_Error(
                'ivan_rate_limited',
                __( 'Too many requests. Please wait a moment before sending another message.', 'ivan-ai-chatbot' ),
                array( 'status' => 429 )
            );
        }

        return true;
    }

    /**
     * Request argument validation and sanitization schema.
     *
     * @return array
     */
    public function get_endpoint_args() {
        return array(
            'message'         => array(
                'required'          => true,
                'type'              => 'string',
                'sanitize_callback' => function( $param ) {
                    return is_string( $param ) ? sanitize_text_field( $param ) : '';
                },
                'validate_callback' => function( $param ) {
                    if ( ! is_string( $param ) ) {
                        return false;
                    }
                    $trimmed = trim( $param );
                    return ! empty( $trimmed ) && mb_strlen( $trimmed ) <= 2000;
                },
            ),
            'conversation_id' => array(
                'required'          => false,
                'type'              => array( 'string', 'null' ),
                'default'           => null,
                'sanitize_callback' => function( $param ) {
                    return ( is_string( $param ) && ! empty( trim( $param ) ) ) ? sanitize_text_field( trim( $param ) ) : null;
                },
                'validate_callback' => function( $param ) {
                    if ( empty( $param ) ) return true;
                    if ( ! is_string( $param ) ) return false;
                    return (bool) preg_match( '/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i', trim( $param ) );
                },
            ),
            'session_id'      => array(
                'required'          => false,
                'type'              => array( 'string', 'null' ),
                'default'           => null,
                'sanitize_callback' => function( $param ) {
                    return ( is_string( $param ) && ! empty( trim( $param ) ) ) ? sanitize_text_field( trim( $param ) ) : null;
                },
                'validate_callback' => function( $param ) {
                    if ( empty( $param ) ) return true;
                    if ( ! is_string( $param ) ) return false;
                    return (bool) preg_match( '/^[a-zA-Z0-9_\-]{4,128}$/', trim( $param ) );
                },
            ),
            'contact_id'      => array(
                'required'          => false,
                'type'              => array( 'string', 'null' ),
                'default'           => null,
                'sanitize_callback' => function( $param ) {
                    return ( is_string( $param ) && ! empty( trim( $param ) ) ) ? sanitize_text_field( trim( $param ) ) : null;
                },
                'validate_callback' => function( $param ) {
                    if ( empty( $param ) ) return true;
                    if ( ! is_string( $param ) ) return false;
                    return (bool) preg_match( '/^[a-zA-Z0-9]{10,64}$/', trim( $param ) );
                },
            ),
            'stream'          => array(
                'required'          => false,
                'type'              => 'boolean',
                'default'           => false,
            ),
        );
    }

    /**
     * Handle incoming chat requests.
     *
     * @param WP_REST_Request $request Incoming REST request.
     * @return WP_REST_Response|WP_Error
     */
    public function handle_chat_request( $request ) {
        try {
            $backend_url = $this->get_backend_url();
            $api_key     = $this->get_api_key();

            if ( empty( $backend_url ) ) {
                return new WP_Error(
                    'ivan_misconfigured',
                    __( 'Ivan Chatbot backend URL is not configured.', 'ivan-ai-chatbot' ),
                    array( 'status' => 503 )
                );
            }

            $raw_message = $request->get_param( 'message' );
            $message     = is_string( $raw_message ) ? trim( $raw_message ) : '';
            if ( empty( $message ) ) {
                return new WP_Error(
                    'invalid_message',
                    __( 'Message cannot be empty.', 'ivan-ai-chatbot' ),
                    array( 'status' => 400 )
                );
            }

            $conversation_id = $request->get_param( 'conversation_id' );
            $session_id      = $request->get_param( 'session_id' );
            $contact_id      = $request->get_param( 'contact_id' );
            $stream          = (bool) $request->get_param( 'stream' );

            // If client requested SSE streaming and server environment supports it
            if ( $stream ) {
                return $this->handle_streaming_request( $backend_url, $api_key, $message, $conversation_id, $session_id, $contact_id );
            }

            // Default Unary Request
            return $this->handle_unary_request( $backend_url, $api_key, $message, $conversation_id, $session_id, $contact_id );
        } catch ( Throwable $e ) {
            error_log( 'Ivan API Error: ' . $e->getMessage() );
            return new WP_Error(
                'ivan_internal_error',
                __( 'An unexpected error occurred while communicating with the Ivan AI service.', 'ivan-ai-chatbot' ),
                array( 'status' => 500, 'error' => $e->getMessage() )
            );
        }
    }

    /**
     * Unary JSON Integration
     * Maps message -> question, sends to backend, returns answer and state to client.
     */
    protected function handle_unary_request( $backend_url, $api_key, $message, $conversation_id, $session_id, $contact_id ) {
        try {
            $target_url = rtrim( $backend_url, '/' ) . '/api/v1/chat';

            $payload = array(
                'question'        => $message,
                'conversation_id' => ! empty( $conversation_id ) ? $conversation_id : null,
                'session_id'      => ! empty( $session_id ) ? $session_id : null,
                'contact_id'      => ! empty( $contact_id ) ? $contact_id : null,
            );

            $headers = array(
                'Content-Type' => 'application/json',
                'Accept'       => 'application/json',
            );

            if ( ! empty( $api_key ) ) {
                $headers['X-Ivan-API-Key'] = $api_key;
            }

            $response = wp_remote_post(
                $target_url,
                array(
                    'headers'     => $headers,
                    'body'        => wp_json_encode( $payload ),
                    'timeout'     => self::BACKEND_TIMEOUT,
                    'sslverify'   => apply_filters( 'ivan_ssl_verify', true ),
                    'httpversion' => '1.1',
                )
            );

            if ( is_wp_error( $response ) ) {
                return new WP_Error(
                    'ivan_backend_unavailable',
                    __( 'Unable to reach the Ivan AI backend. Please verify backend connection.', 'ivan-ai-chatbot' ),
                    array( 'status' => 502, 'debug' => $response->get_error_message() )
                );
            }

            $status_code = wp_remote_retrieve_response_code( $response );
            $body        = wp_remote_retrieve_body( $response );
            $data        = json_decode( $body, true );

            if ( $status_code === 401 || $status_code === 403 ) {
                return new WP_Error(
                    'ivan_auth_failure',
                    __( 'Authentication failed between WordPress and the Ivan AI backend.', 'ivan-ai-chatbot' ),
                    array( 'status' => 500 )
                );
            }

            if ( $status_code >= 400 || empty( $data ) ) {
                $err_msg = isset( $data['detail'] ) ? ( is_string( $data['detail'] ) ? $data['detail'] : wp_json_encode( $data['detail'] ) ) : __( 'Error communicating with Ivan AI service.', 'ivan-ai-chatbot' );
                return new WP_Error(
                    'ivan_backend_error',
                    $err_msg,
                    array( 'status' => $status_code >= 400 ? $status_code : 500 )
                );
            }

            // Map backend response: 'answer' -> 'answer' and 'reply'
            return new WP_REST_Response(
                array(
                    'success'         => true,
                    'answer'          => isset( $data['answer'] ) ? $data['answer'] : '',
                    'reply'           => isset( $data['answer'] ) ? $data['answer'] : '',
                    'conversation_id' => isset( $data['conversation_id'] ) ? $data['conversation_id'] : $conversation_id,
                    'session_id'      => isset( $data['session_id'] ) ? $data['session_id'] : $session_id,
                    'status'          => isset( $data['status'] ) ? $data['status'] : 'success',
                ),
                200
            );
        } catch ( Throwable $e ) {
            error_log( 'Ivan Unary Request Exception: ' . $e->getMessage() );
            return new WP_Error(
                'ivan_unary_exception',
                $e->getMessage(),
                array( 'status' => 500 )
            );
        }
    }

    /**
     * Real-Time SSE Streaming Handler
     * Proxies Server-Sent Events from FastAPI directly to the client without buffering.
     */
    protected function handle_streaming_request( $backend_url, $api_key, $message, $conversation_id, $session_id, $contact_id ) {
        $query_args = array(
            'question' => $message,
        );
        if ( ! empty( $conversation_id ) ) {
            $query_args['conversation_id'] = $conversation_id;
        }
        if ( ! empty( $session_id ) ) {
            $query_args['session_id'] = $session_id;
        }
        if ( ! empty( $contact_id ) ) {
            $query_args['contact_id'] = $contact_id;
        }

        $stream_url = rtrim( $backend_url, '/' ) . '/api/v1/chat/stream?' . http_build_query( $query_args );

        // Close any existing PHP output buffers and disable compression buffering
        @ini_set( 'zlib.output_compression', '0' );
        @ini_set( 'output_buffering', 'off' );
        @ini_set( 'implicit_flush', '1' );
        if ( function_exists( 'ob_implicit_flush' ) ) {
            @ob_implicit_flush( 1 );
        }
        while ( ob_get_level() > 0 ) {
            @ob_end_clean();
        }

        // Send streaming headers to browser
        header( 'Content-Type: text/event-stream; charset=utf-8' );
        header( 'Cache-Control: no-cache, no-transform' );
        header( 'Connection: keep-alive' );
        header( 'Content-Encoding: none' );
        header( 'X-Accel-Buffering: no' ); // Disable buffering in Nginx

        // Ensure session locks or PHP execution timeouts don't kill stream
        @set_time_limit( 0 );
        if ( function_exists( 'session_write_close' ) ) {
            session_write_close();
        }

        $headers = array(
            'Accept: text/event-stream',
        );
        if ( ! empty( $api_key ) ) {
            $headers[] = 'X-Ivan-API-Key: ' . $api_key;
        }

        // Strategy 1: cURL streaming if extension is loaded
        if ( function_exists( 'curl_init' ) ) {
            $ch = curl_init();
            curl_setopt( $ch, CURLOPT_URL, $stream_url );
            curl_setopt( $ch, CURLOPT_HTTPGET, true );
            curl_setopt( $ch, CURLOPT_RETURNTRANSFER, false );
            curl_setopt( $ch, CURLOPT_TIMEOUT, 120 );
            curl_setopt( $ch, CURLOPT_FOLLOWLOCATION, true );
            curl_setopt( $ch, CURLOPT_SSL_VERIFYPEER, apply_filters( 'ivan_ssl_verify', true ) );
            curl_setopt( $ch, CURLOPT_HTTPHEADER, $headers );

            curl_setopt( $ch, CURLOPT_WRITEFUNCTION, function( $handle, $chunk ) {
                echo $chunk;
                if ( function_exists( 'flush' ) ) {
                    @flush();
                }
                return strlen( $chunk );
            });

            $success = curl_exec( $ch );
            if ( ! $success ) {
                $error = curl_error( $ch );
                echo "data: " . wp_json_encode( array( 'type' => 'error', 'message' => 'Stream connection failed: ' . $error ) ) . "\n\n";
                if ( function_exists( 'flush' ) ) {
                    @flush();
                }
            }
            curl_close( $ch );
            exit;
        }

        // Strategy 2: fopen with stream_context fallback
        $context = stream_context_create( array(
            'http' => array(
                'method'        => 'GET',
                'header'        => implode( "\r\n", $headers ),
                'timeout'       => 120,
                'ignore_errors' => true,
            ),
        ) );

        $stream_handle = @fopen( $stream_url, 'r', false, $context );
        if ( $stream_handle ) {
            while ( ! feof( $stream_handle ) ) {
                $chunk = fread( $stream_handle, 1024 );
                if ( false !== $chunk && strlen( $chunk ) > 0 ) {
                    echo $chunk;
                    if ( function_exists( 'flush' ) ) {
                        @flush();
                    }
                }
            }
            fclose( $stream_handle );
            exit;
        }

        echo "data: " . wp_json_encode( array( 'type' => 'error', 'message' => 'Unable to establish streaming connection (cURL and stream wrappers unavailable).' ) ) . "\n\n";
        if ( function_exists( 'flush' ) ) {
            @flush();
        }
        exit;
    }

    /**
     * IP-based rate limiting check.
     */
    protected function is_rate_limited( $client_ip ) {
        if ( empty( $client_ip ) ) {
            return false;
        }

        $transient_key = 'ivan_rl_' . md5( $client_ip );
        $count = (int) get_transient( $transient_key );

        if ( false === $count || 0 === $count ) {
            set_transient( $transient_key, 1, self::RATE_LIMIT_WINDOW );
            return false;
        }

        if ( $count >= self::RATE_LIMIT_MAX ) {
            return true;
        }

        set_transient( $transient_key, $count + 1, self::RATE_LIMIT_WINDOW );
        return false;
    }

    /**
     * Get client IP address safely.
     */
    protected function get_client_ip() {
        if ( ! empty( $_SERVER['HTTP_CLIENT_IP'] ) ) {
            return sanitize_text_field( wp_unslash( $_SERVER['HTTP_CLIENT_IP'] ) );
        }
        if ( ! empty( $_SERVER['HTTP_X_FORWARDED_FOR'] ) ) {
            $ips = explode( ',', sanitize_text_field( wp_unslash( $_SERVER['HTTP_X_FORWARDED_FOR'] ) ) );
            return trim( $ips[0] );
        }
        if ( ! empty( $_SERVER['REMOTE_ADDR'] ) ) {
            return sanitize_text_field( wp_unslash( $_SERVER['REMOTE_ADDR'] ) );
        }
        return '127.0.0.1';
    }

    /**
     * Retrieve configured Ivan Backend URL.
     */
    public function get_backend_url() {
        $url = class_exists( 'Ivan_Settings' ) ? Ivan_Settings::get_option( 'api_url', '' ) : '';
        if ( empty( $url ) ) {
            $url = get_option( 'ivan_api_url', '' );
        }
        if ( empty( $url ) && defined( 'IVAN_API_URL' ) ) {
            $url = IVAN_API_URL;
        }
        return apply_filters( 'ivan_backend_url', $url );
    }

    /**
     * Retrieve configured Ivan API Key.
     */
    public function get_api_key() {
        $key = class_exists( 'Ivan_Settings' ) ? Ivan_Settings::get_option( 'api_key', '' ) : '';
        if ( empty( $key ) ) {
            $key = get_option( 'ivan_api_key', '' );
        }
        if ( empty( $key ) && defined( 'IVAN_API_KEY' ) ) {
            $key = IVAN_API_KEY;
        }
        return apply_filters( 'ivan_api_key', $key );
    }
}

