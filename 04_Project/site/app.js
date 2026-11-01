/* AI 日报 —— 纯前端渲染。数据来自构建时生成的 data.js。
   没有构建产物时这里什么都不做，页面显示提示，不留白屏。 */

(function () {
  'use strict';

  var DATA = window.DIGEST || { index: [], issues: {} };
  var app = document.getElementById('app');
  var nav = document.getElementById('sessions');
  // 必须与 build.EMBED_RECENT 一致：按钮数超过内嵌期次数，离线点开就是空的。
  // 这个值由构建时写进 data.js，不再两边各写一份。
  var MAX_CHIPS = DATA.embedLimit || 14;
  var currentId = '';

  var WEEK = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

  /* ── 已读记录（只存本机，不上传） ───────────── */

  function readKey(id) {
    return 'aidigest:read:' + id;
  }

  function readSet(id) {
    try {
      return new Set(JSON.parse(localStorage.getItem(readKey(id)) || '[]'));
    } catch (e) {
      return new Set();
    }
  }

  function markRead(issueId, itemId) {
    var set = readSet(issueId);
    if (set.has(itemId)) return;
    set.add(itemId);
    try {
      localStorage.setItem(readKey(issueId), JSON.stringify([].slice.call(set)));
    } catch (e) {
      /* 隐私模式下写不进去，忽略即可 */
    }
  }

  /* ── 工具 ──────────────────────────────────── */

  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // 链接来自外部 RSS，不可信：只放行 http(s)，其余一律不给跳。
  // 否则 javascript: 开头的 url 会被当脚本执行。
  function safeUrl(url) {
    return /^https?:\/\//i.test(String(url || '')) ? url : '#';
  }

  function parseDate(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }

  function dateTitle(issue) {
    var d = parseDate(issue.date + 'T00:00:00');
    if (!d) return issue.date;
    return d.getMonth() + 1 + ' 月 ' + d.getDate() + ' 日 · ' + WEEK[d.getDay()];
  }

  function timeLabel(iso, issueDate) {
    var d = parseDate(iso);
    if (!d) return '';
    var hh = String(d.getHours()).padStart(2, '0');
    var mm = String(d.getMinutes()).padStart(2, '0');
    var local = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
      '-' + String(d.getDate()).padStart(2, '0');
    return local === issueDate ? hh + ':' + mm : local.slice(5) + ' ' + hh + ':' + mm;
  }

  function chipLabel(entry) {
    var d = parseDate(entry.date + 'T00:00:00');
    return d ? (d.getMonth() + 1) + '/' + d.getDate() : entry.date;
  }

  function emptyBlock(title, hint) {
    app.innerHTML = '<div class="empty"><strong>' + esc(title) + '</strong>' +
      esc(hint) + '</div>';
  }

  /* ── 渲染一期 ──────────────────────────────── */

  function renderIssue(issue, entry) {
    var set = readSet(issue.id);

    var head = '<div class="dateline"><h1>' + esc(dateTitle(issue)) + '</h1>' +
      '<span class="sub">' + issue.count + ' 条</span></div>';

    var intro = issue.has_ai_summary
      ? '<p class="intro">按重要度排序，点标题看原文。</p>'
      : '<p class="intro">本期尚未生成中文摘要，标题为原文语言。</p>';

    if (!issue.count) {
      app.innerHTML = head + '<div class="empty"><strong>今天没有新动静</strong>' +
        '抓取到了，但没有符合口径的新消息，明天再看。</div>';
      return;
    }

    var lis = issue.items.map(function (item, i) {
      var title = item.title_zh || item.title_orig;
      var lead = i < 3 ? ' lead' : '';
      var read = set.has(item.id) ? ' read' : '';
      var summary = item.summary
        ? '<p class="sum">' + esc(item.summary) + '</p>'
        : '';
      return '<li class="item' + lead + read + '" data-id="' + esc(item.id) + '">' +
        '<div class="num">' + String(i + 1).padStart(2, '0') + '</div>' +
        '<div class="body">' +
          '<div class="meta">' +
            '<span class="cat">' + esc(item.category) + '</span>' +
            '<span class="src">' + esc(item.source) + '</span>' +
            '<time datetime="' + esc(item.published) + '">' +
              esc(timeLabel(item.published, issue.date)) + '</time>' +
          '</div>' +
          '<h2 class="title"><a href="' + esc(safeUrl(item.url)) + '" target="_blank" ' +
            'rel="noopener noreferrer">' + esc(title) + '</a></h2>' +
          summary +
        '</div></li>';
    }).join('');

    app.innerHTML = head + intro + '<ol class="list">' + lis + '</ol>';
  }

  /* ── 期次导航 ──────────────────────────────── */

  function renderChips(currentId) {
    var entries = DATA.index.slice(0, MAX_CHIPS);
    nav.innerHTML = entries.map(function (entry) {
      var current = entry.id === currentId ? ' aria-current="true"' : '';
      return '<button class="chip" type="button" data-id="' + esc(entry.id) + '"' +
        current + '>' + esc(chipLabel(entry)) + '</button>';
    }).join('');
  }

  /* ── 载入 ──────────────────────────────────── */

  function findEntry(id) {
    for (var i = 0; i < DATA.index.length; i++) {
      if (DATA.index[i].id === id) return DATA.index[i];
    }
    return null;
  }

  /* file:// 下 history.replaceState 会抛 SecurityError，
     一抛就挡住后面所有渲染（页面卡在「正在载入」）。
     本地双击打开是这个站明确支持的用法，所以这里必须降级到改 hash。 */
  function setHash(id) {
    var target = '#' + id;
    if (location.hash === target) return;
    try {
      history.replaceState(null, '', target);
    } catch (e) {
      try { location.hash = target; } catch (e2) { /* 连 hash 都不让改就算了 */ }
    }
  }

  function show(id) {
    var entry = findEntry(id);
    if (!entry) return false;

    currentId = id;
    renderChips(id);
    setHash(id);

    if (DATA.issues[id]) {
      renderIssue(DATA.issues[id], entry);
      window.scrollTo(0, 0);
      return true;
    }

    // 超出内嵌范围的老期次：在线时按需抓取
    app.innerHTML = '<p class="empty">正在载入历史期次…</p>';
    fetch('data/issues/' + id + '.json')
      .then(function (res) { return res.ok ? res.json() : Promise.reject(); })
      .then(function (issue) { renderIssue(issue, entry); })
      .catch(function () {
        emptyBlock('这一期不在离线包里', '连上网络后可以查看，或直接打开 data/issues/' + id + '.json。');
      });
    return true;
  }

  /* ── 事件 ──────────────────────────────────── */

  nav.addEventListener('click', function (event) {
    var chip = event.target.closest('.chip');
    if (chip) show(chip.dataset.id);
  });

  app.addEventListener('click', function (event) {
    var link = event.target.closest('a');
    if (!link) return;
    var li = link.closest('.item');
    if (!li) return;
    // 用渲染时记下的期次 id，不依赖 location.hash——
    // file:// 下 hash 可能改不动
    markRead(currentId, li.dataset.id);
    li.classList.add('read');
  });

  window.addEventListener('hashchange', function () {
    show(location.hash.slice(1));
  });

  /* ── 启动 ──────────────────────────────────── */

  if (!DATA.index.length) {
    emptyBlock('还没有任何一期', '第一次抓取完成后，这里会出现今天的内容。');
    return;
  }

  var wanted = location.hash.slice(1);
  if (!show(wanted)) show(DATA.index[0].id);

  var built = document.getElementById('built');
  if (built && DATA.generatedAt) {
    built.textContent = '构建于 ' + DATA.generatedAt.replace('T', ' ').slice(0, 16);
  }
})();
