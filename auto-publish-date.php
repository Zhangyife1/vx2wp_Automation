<?php
/**
 * Plugin Name: Auto Publish Date from HTML Comment
 * Description: 自动从文章HTML注释 <!-- 发布时间：YYYY年M月D日 HH:MM --> 中提取发布时间并设为文章日期
 * Version: 1.0
 * 
 * 使用方式：在文章内容中包含注释 <!-- 发布时间：2026年5月12日 18:09 -->
 * 保存/发布文章时，插件会自动：
 *   1. 提取时间并设为文章发布时间
 *   2. 从内容中删除该注释（避免页面显示）
 */

// 防止直接访问
if (!defined('ABSPATH')) {
    exit;
}

/**
 * 从文章内容中提取发布时间注释，并更新文章日期
 * 钩入 save_post，仅在前端编辑器保存时触发
 */
add_action('save_post', 'apd_extract_and_set_date', 10, 3);

function apd_extract_and_set_date($post_id, $post, $update) {
    // 避免自动保存和修订版本触发
    if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) return;
    if (wp_is_post_revision($post_id)) return;
    if ($post->post_type !== 'post') return;
    
    $content = $post->post_content;
    
    // 匹配注释：<!-- 发布时间：2026年5月12日 18:09 -->
    // 支持格式：YYYY年M月D日 H:MM 或 YYYY年MM月DD日 HH:MM
    if (!preg_match('/<!--\s*发布时间[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*(\d{1,2})\s*[:：]\s*(\d{2})\s*-->/', $content, $matches)) {
        return;
    }
    
    $year   = intval($matches[1]);
    $month  = intval($matches[2]);
    $day    = intval($matches[3]);
    $hour   = intval($matches[4]);
    $minute = intval($matches[5]);
    
    // 构造 WP 日期格式
    $post_date = sprintf('%04d-%02d-%02d %02d:%02d:00', $year, $month, $day, $hour, $minute);
    
    // 从内容中移除注释行（包括前面的空行和换行）
    $clean_content = preg_replace('/\s*<!--\s*发布时间[：:]\s*\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{2}\s*-->\s*/', "\n", $content);
    $clean_content = trim($clean_content);
    
    // 更新文章：设置发布时间 + 清理注释
    // 使用 wp_update_post 会再次触发 save_post，需要先移除钩子避免无限循环
    remove_action('save_post', 'apd_extract_and_set_date', 10);
    
    wp_update_post(array(
        'ID'            => $post_id,
        'post_date'     => $post_date,
        'post_date_gmt' => get_gmt_from_date($post_date),
        'post_content'  => $clean_content,
    ));
    
    // 重新挂载钩子
    add_action('save_post', 'apd_extract_and_set_date', 10, 3);
    
    // 记录日志（可在 WP调试日志中查看）
    if (defined('WP_DEBUG') && WP_DEBUG) {
        error_log("[AutoPublishDate] 文章#{$post_id} 发布时间已设为: {$post_date}");
    }
}
