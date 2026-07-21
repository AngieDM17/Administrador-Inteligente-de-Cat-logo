<?php
/**
 * Ekipon — Shortcodes dinámicos para las plantillas Elementor.
 *
 * Cada shortcode lee los datos que el Publicador ya guardó en cada producto
 * (meta con prefijo "ekipon_") y dibuja SU pieza. Así las plantillas de
 * Elementor dejan de llenarse a mano: el diseño queda en Elementor y los datos
 * se completan solos, por producto.
 *
 * Instalación: pegar este código en un snippet de "Code Snippets"
 * (Snippets → Añadir nuevo), sin la primera línea "<?php". Ejecutar en todo el
 * sitio ("Run everywhere"). Es 100% reversible: desactivando el snippet, todo
 * vuelve como estaba.
 *
 * Shortcodes:
 *   [banner_ekipon]          → el banner del producto
 *   [ficha_tecnica_ekipon]   → la tabla de ficha técnica
 *   [caracteristicas_ekipon] → la lista de características
 *   [video_ekipon]           → el video de YouTube
 *
 * Todos aceptan un atributo opcional id="123" para forzar un producto puntual
 * (por defecto usan el producto de la página actual).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit; // Sin acceso directo.
}

/**
 * Resuelve el ID del producto: el atributo id="" si viene, si no el post
 * actual, si no el objeto consultado. Devuelve 0 si no hay contexto.
 */
function ekipon_id_producto( $atts ) {
	if ( ! empty( $atts['id'] ) && is_numeric( $atts['id'] ) ) {
		return (int) $atts['id'];
	}
	$id = get_the_ID();
	if ( $id ) {
		return (int) $id;
	}
	return (int) get_queried_object_id();
}

/**
 * Lee una meta del producto. Devuelve '' si no hay.
 */
function ekipon_meta( $id, $clave ) {
	if ( ! $id ) {
		return '';
	}
	$valor = get_post_meta( $id, $clave, true );
	return is_string( $valor ) ? $valor : '';
}

/**
 * Decodifica una meta guardada como JSON. Devuelve array vacío si la meta está
 * vacía, si el JSON es inválido, o si no decodifica a un array.
 */
function ekipon_json( $id, $clave ) {
	$crudo = ekipon_meta( $id, $clave );
	if ( '' === $crudo ) {
		return array();
	}
	$datos = json_decode( $crudo, true );
	return is_array( $datos ) ? $datos : array();
}

/**
 * Inyecta una vez, por página, un CSS mínimo para las piezas. Es discreto:
 * el look principal lo dan tu tema y Elementor; esto solo garantiza legibilidad
 * si un widget queda sin estilo.
 */
function ekipon_estilos_una_vez() {
	static $ya = false;
	if ( $ya ) {
		return '';
	}
	$ya = true;
	return '<style>'
		. '.ekipon-ficha-tecnica{width:100%;border-collapse:collapse}'
		. '.ekipon-ficha-tecnica th,.ekipon-ficha-tecnica td{padding:8px 12px;'
		. 'border-bottom:1px solid rgba(0,0,0,.08);text-align:left;vertical-align:top}'
		. '.ekipon-ficha-tecnica th{white-space:nowrap;width:38%;font-weight:600}'
		. '.ekipon-caracteristicas{margin:0;padding-left:1.2em}'
		. '.ekipon-caracteristicas li{margin:.25em 0}'
		. '.ekipon-banner img{max-width:100%;height:auto;display:block}'
		. '.ekipon-video{position:relative;padding-top:56.25%}'
		. '.ekipon-video iframe{position:absolute;inset:0;width:100%;height:100%}'
		. '</style>';
}

/**
 * [banner_ekipon] — imagen del banner del producto.
 */
function ekipon_sc_banner( $atts ) {
	$id  = ekipon_id_producto( $atts );
	$url = ekipon_meta( $id, 'ekipon_banner_url' );
	if ( '' === $url ) {
		return '';
	}
	$alt = get_the_title( $id );
	return ekipon_estilos_una_vez()
		. '<figure class="ekipon-banner"><img src="' . esc_url( $url ) . '" alt="'
		. esc_attr( $alt ) . '" loading="lazy" /></figure>';
}
add_shortcode( 'banner_ekipon', 'ekipon_sc_banner' );

/**
 * [ficha_tecnica_ekipon] — tabla de especificaciones.
 */
function ekipon_sc_ficha_tecnica( $atts ) {
	$id    = ekipon_id_producto( $atts );
	$filas = ekipon_json( $id, 'ekipon_ficha_tecnica' );
	if ( empty( $filas ) ) {
		return '';
	}
	$html = '<table class="ekipon-ficha-tecnica"><tbody>';
	foreach ( $filas as $clave => $valor ) {
		if ( ! is_scalar( $valor ) ) {
			continue; // Solo valores simples: nunca "Array" ni warnings de PHP.
		}
		$html .= '<tr><th scope="row">' . esc_html( (string) $clave )
			. '</th><td>' . esc_html( (string) $valor ) . '</td></tr>';
	}
	$html .= '</tbody></table>';
	return ekipon_estilos_una_vez() . $html;
}
add_shortcode( 'ficha_tecnica_ekipon', 'ekipon_sc_ficha_tecnica' );

/**
 * [caracteristicas_ekipon] — lista de características.
 */
function ekipon_sc_caracteristicas( $atts ) {
	$id    = ekipon_id_producto( $atts );
	$items = ekipon_json( $id, 'ekipon_caracteristicas' );
	if ( empty( $items ) ) {
		return '';
	}
	$html = '<ul class="ekipon-caracteristicas">';
	foreach ( $items as $item ) {
		if ( ! is_scalar( $item ) ) {
			continue; // Solo valores simples: nunca "Array" ni warnings de PHP.
		}
		$texto = trim( (string) $item );
		if ( '' !== $texto ) {
			$html .= '<li>' . esc_html( $texto ) . '</li>';
		}
	}
	$html .= '</ul>';
	return ekipon_estilos_una_vez() . $html;
}
add_shortcode( 'caracteristicas_ekipon', 'ekipon_sc_caracteristicas' );

/**
 * [video_ekipon] — video de YouTube embebido y responsive.
 */
function ekipon_sc_video( $atts ) {
	$id  = ekipon_id_producto( $atts );
	$url = ekipon_meta( $id, 'ekipon_video_url' );
	if ( '' === $url ) {
		return '';
	}
	$embed = wp_oembed_get( esc_url_raw( $url ) );
	if ( $embed ) {
		return ekipon_estilos_una_vez()
			. '<div class="ekipon-video">' . $embed . '</div>';
	}
	// Sin embed disponible: enlace simple, seguro.
	return '<p class="ekipon-video-enlace"><a href="' . esc_url( $url )
		. '" target="_blank" rel="noopener noreferrer">Ver video del producto</a></p>';
}
add_shortcode( 'video_ekipon', 'ekipon_sc_video' );
