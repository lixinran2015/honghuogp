<template>
  <div class="container mx-auto px-4 py-6 space-y-6">
    <!-- 标题区 -->
    <div>
      <h1 class="text-2xl font-bold text-gray-900">主线龙头 · 龙头买点策略说明</h1>
      <p class="text-sm text-gray-500 mt-1">
        面向做主线/龙头接力的短线交易者，统一一套「主线强度 + 龙头角色 + 买点」的标准化打法，并用历史回测给出大致可期待的区间表现。
      </p>
    </div>

    <!-- 一、适用人群与定位 -->
    <section class="bg-white rounded-xl shadow border border-gray-100 p-5">
      <h2 class="text-lg font-semibold text-gray-800 mb-2">一、适用人群与策略定位</h2>
      <ul class="list-disc list-inside text-sm text-gray-700 space-y-1">
        <li>有一定短线经验，关注「主线 / 龙头」和「情绪周期」，但不想只靠盘感瞎追高。</li>
        <li>接受用「右侧确认 + 缩量回踩」等规则来约束自己，愿意牺牲部分收益换稳定性。</li>
        <li>交易风格偏「主线龙头 + 低位启动」，更看重在主线中的位置和持续性。</li>
      </ul>
      <p class="mt-2 text-[11px] text-gray-400">
        风险提示：本策略偏短线趋势跟随 + 主线轮动，对盘中波动和退潮节奏较为敏感，不适合完全被动型、长期死拿型用户。
      </p>
    </section>

    <!-- 二、策略核心逻辑 -->
    <section class="bg-white rounded-xl shadow border border-gray-100 p-5 space-y-3">
      <h2 class="text-lg font-semibold text-gray-800">二、策略核心逻辑：主线 + 龙头 + 买点</h2>

      <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-1">1. 主线强度</h3>
        <p class="text-sm text-gray-700">
          每个交易日，对全市场板块（行业 / 题材 / 指数风格）打出一个
          <span class="font-medium">主线强度分数</span>，综合考虑：
        </p>
        <ul class="list-disc list-inside text-sm text-gray-700 mt-1 space-y-1">
          <li>近期信号次数与集中度（越集中越可能是当下主线）。</li>
          <li>覆盖股票数量与连续活跃天数。</li>
          <li>板块内部龙头股的表现（空间龙头/补涨龙/刚启动等）。</li>
        </ul>
        <p class="mt-1 text-sm text-gray-700">
          实盘和回测统一使用<span class="font-medium">「主线强度前 10」</span>的板块作为标的池，尽量把精力放在当下最有交易价值的少数方向上。
        </p>
      </div>

      <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-1">2. 龙头角色</h3>
        <p class="text-sm text-gray-700">
          在每条主线内部，根据高度 / 启动时间 / 强势程度，将核心个股分为：
        </p>
        <ul class="list-disc list-inside text-sm text-gray-700 mt-1 space-y-1">
          <li><span class="font-medium">空间龙头</span>：连板高度最高、走得最强的票，主线「旗帜」。</li>
          <li><span class="font-medium">补涨龙</span>：跟随空间龙头之后启动，走出第二波高度的票。</li>
          <li><span class="font-medium">刚启动龙头</span>：刚刚完成第一波放量突破，具备成为龙头的潜力。</li>
          <li><span class="font-medium">跟风</span>：跟随上面几类的次级标的，主要用于观察情绪，而非重点买点。</li>
        </ul>
        <p class="mt-1 text-sm text-gray-700">
          策略回测与「龙头跟踪」页面，都围绕<span class="font-medium">空间龙头 + 刚启动龙头</span>两个角色来选股。
        </p>
      </div>

      <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-1">3. 买点规则（v1 简化版）</h3>
        <p class="text-sm text-gray-700">
          在「主线前 10 + 龙头角色」的基础上，对个股的日线走法进行二次筛选，拆分为左右两类买点：
        </p>
        <ul class="list-disc list-inside text-sm text-gray-700 mt-1 space-y-1">
          <li>
            <span class="font-medium">左侧：缩量回踩</span>（isPullbackCandidate）<br />
            条件示意：围绕 20 日线小幅回踩（-3% ~ -10%）、量能萎缩（5 日均量 / 20 日均量 ≤ 0.8），成交额过低的票会被过滤。
          </li>
          <li>
            <span class="font-medium">右侧：确认买点</span>（isBuyCandidate）<br />
            在缩量回踩基础上，出现 1%~3% 的温和上涨、成交额 ≥ 2 亿，视为右侧确认信号。
          </li>
        </ul>
        <p class="mt-1 text-[11px] text-gray-400">
          具体参数（阈值）可以按市场环境迭代调整，回测模块的作用是帮助你量化观察「这套参数在最近一年大致是什么水平」。
        </p>
      </div>
    </section>

    <!-- 三、回测方法与假设 -->
    <section class="bg-white rounded-xl shadow border border-gray-100 p-5 space-y-3">
      <h2 class="text-lg font-semibold text-gray-800">三、回测方法与主要假设</h2>

      <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-1">1. 事件级回测，而非组合模拟</h3>
        <p class="text-sm text-gray-700">
          当前版本为<span class="font-medium">事件级回测</span>：对每一条买点信号单独计算固定持有期（5/10 日）的收益与回撤，
          <span class="font-medium">不构建资金曲线和仓位</span>，因此不会涉及「同一天买几只」「总仓位多少」的问题。
        </p>
      </div>

      <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-1">2. 价格与成本模型</h3>
        <ul class="list-disc list-inside text-sm text-gray-700 space-y-1">
          <li>入场价：默认使用<span class="font-medium">信号日收盘价（close）</span>作为入场价格。</li>
          <li>持有期：持有到第 5 / 第 10 个交易日的收盘价，分别计算 5 日 / 10 日收益。</li>
          <li>交易成本：统一假设双边合计约
            <span class="font-medium">0.2% 成本</span>（买入 0.1% + 卖出 0.1%），净收益字段已扣除该成本。
          </li>
        </ul>
      </div>

      <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-1">3. 回测指标与分层</h3>
        <p class="text-sm text-gray-700">
          回测结果主要围绕以下指标展开：
        </p>
        <ul class="list-disc list-inside text-sm text-gray-700 mt-1 space-y-1">
          <li>5 日 / 10 日净收益的均值、中位数、胜率、尾部 5% 均值（风险尾部）。</li>
          <li>按主线强度（4~5、5~6、6~7、7+）分桶对比收益。</li>
          <li>按市场环境（偏多 / 震荡 / 偏空）分层观察表现差异。</li>
          <li>按信号类型（右侧 / 缩量）对比谁「更值得重仓」。</li>
        </ul>
      </div>

      <div>
        <h3 class="text-sm font-semibold text-gray-700 mb-1">4. 基准与超额收益</h3>
        <p class="text-sm text-gray-700">
          每条信号同时记录沪深 300（000300.SH）同期 5 日 / 10 日收益，用于后续观察超额收益（目前已在数据结构中预留）。
        </p>
      </div>
    </section>

    <!-- 四、推荐工作流 -->
    <section class="bg-white rounded-xl shadow border border-gray-100 p-5 space-y-3">
      <h2 class="text-lg font-semibold text-gray-800">四、推荐的日常使用流程</h2>

      <ol class="list-decimal list-inside text-sm text-gray-700 space-y-1">
        <li>
          <span class="font-medium">盘前 / 盘后：主线雷达</span> — 在「主线雷达」页面查看主线强度前 10，锁定 1~2 条当下主线。
        </li>
        <li>
          <span class="font-medium">选票：龙头跟踪</span> — 在「龙头跟踪」中，只看主线前 10 下的空间龙头 / 刚启动龙头，结合买点提示筛出候选票。
        </li>
        <li>
          <span class="font-medium">验证：龙头买点回测</span> — 进入「龙头买点回测」：
          <ul class="list-disc list-inside ml-4 space-y-0.5">
            <li>用「推荐组合」预设（右侧 + 最近 6 个月）看整体表现。</li>
            <li>看右侧 vs 缩量 在当前窗口下的收益 / 胜率差异。</li>
            <li>看牛市 vs 熊市分层表现，决定当前环境下仓位要不要缩。</li>
          </ul>
        </li>
        <li>
          <span class="font-medium">执行与复盘：股票跟踪 + 诊股</span> — 把看好的票加入「股票跟踪」，盘中在跟踪池和诊股页内盯盘，
          通过诊股页的小卡片随时回顾该股在龙头买点体系中的历史表现。
        </li>
      </ol>
    </section>

    <!-- 五、风险提示 -->
    <section class="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
      <h2 class="text-sm font-semibold text-yellow-800 mb-1">五、重要风险提示</h2>
      <ul class="list-disc list-inside text-xs text-yellow-800 space-y-1">
        <li>所有回测结果基于历史数据和统一的执行/成本假设，不构成对未来收益的任何承诺。</li>
        <li>事件级回测只反映单个买点的大致收益/风险分布，不代表真实资金曲线的波动。</li>
        <li>实际交易需结合个人风险承受能力、资金体量、盘中流动性和情绪变化自行决策。</li>
      </ul>
    </section>
  </div>
</template>

<script setup>
</script>

<style scoped>
</style>

