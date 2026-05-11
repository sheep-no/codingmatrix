<template>
  <div v-if="visible" class="chart-editor-overlay" @click.self="closeEditor">
    <div class="chart-editor-container">
      <!-- 头部 -->
      <div class="editor-header">
        <div class="header-left">
          <h2>📊 图表编辑器</h2>
          <div v-if="charts.length > 0" class="header-stats">
            <span class="stat-item">图表: {{ charts.length }}</span>
            <span class="stat-item">数据源: {{ dataSources.length }}</span>
          </div>
        </div>
        <div class="header-right">
          <button
            class="header-btn"
            :title="isDarkTheme ? '切换亮色' : '切换深色'"
            @click="toggleTheme"
          >
            {{ isDarkTheme ? '[MOON]' : '[SUN]' }}
          </button>
          <button class="header-btn" title="帮助" @click="showHelp = true">❓</button>
          <button class="close-btn" @click="closeEditor">✕</button>
        </div>
      </div>

      <!-- 主内容区 -->
      <div class="editor-content" :class="{ 'dark-theme': isDarkTheme }">
        <!-- 左侧配置面板 -->
        <div class="config-panel">
          <!-- 数据导入 -->
          <div class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">📁</span>
              <span>数据导入</span>
              <button class="collapse-btn" @click="toggleSection('dataImport')">
                {{ collapsedSections.dataImport ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.dataImport">
              <div
                class="upload-area"
                @dragover.prevent
                @drop.prevent="handleFileDrop"
                @click="handleUploadClick"
              >
                <input
                  ref="fileInput"
                  type="file"
                  accept=".xlsx,.xls,.csv,.json"
                  multiple
                  style="display: none"
                  @change="handleFileSelect"
                />
                <div class="upload-content">
                  <span class="upload-icon">📤</span>
                  <p>拖拽文件到此处或点击上传</p>
                  <p class="upload-hint">支持 .xlsx, .xls, .csv, .json 格式</p>
                </div>
              </div>

              <!-- 已导入的数据源列表 -->
              <div v-if="dataSources.length > 0" class="data-sources-list">
                <div
                  v-for="(source, index) in dataSources"
                  :key="index"
                  class="data-source-item"
                  :class="{ active: selectedDataSourceIndex === index }"
                  @click="selectDataSource(index)"
                >
                  <span class="source-icon">📊</span>
                  <div class="source-info">
                    <span class="source-name">{{ source.name }}</span>
                    <span class="source-rows"
                      >{{ source.data.length }} 条数据 · {{ source.fields.length }} 字段</span
                    >
                  </div>
                  <button class="remove-btn" title="Delete" @click.stop="removeDataSource(index)">
                    <span>[DEL]</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- 图表类型选择 -->
          <div class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">🎨</span>
              <span>图表类型</span>
              <button class="collapse-btn" @click="toggleSection('chartType')">
                {{ collapsedSections.chartType ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.chartType">
              <div class="chart-type-grid">
                <div
                  v-for="type in chartTypes"
                  :key="type.value"
                  class="chart-type-card"
                  :class="{ active: config.chartType === type.value }"
                  :title="type.label"
                  @click="selectChartType(type.value)"
                >
                  <span class="chart-type-icon">{{ type.icon }}</span>
                  <span class="chart-type-name">{{ type.label }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 数据字段配置 -->
          <div v-if="currentDataSource" class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">[CONFIG]</span>
              <span>数据配置</span>
              <button class="collapse-btn" @click="toggleSection('dataConfig')">
                {{ collapsedSections.dataConfig ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.dataConfig">
              <div class="field-config">
                <div class="field-group">
                  <label class="field-label">
                    <span>X 轴字段</span>
                    <span class="required">*</span>
                  </label>
                  <div class="select-wrapper">
                    <select v-model="config.xAxis" class="field-select" @change="updateChart">
                      <option value="">请选择</option>
                      <option v-for="field in currentDataSource.fields" :key="field" :value="field">
                        {{ field }}
                      </option>
                    </select>
                  </div>
                </div>

                <div class="field-group">
                  <label class="field-label">
                    <span>Y 轴字段</span>
                    <span class="required">*</span>
                  </label>
                  <div class="select-wrapper">
                    <select v-model="config.yAxis" class="field-select" @change="updateChart">
                      <option value="">请选择</option>
                      <option v-for="field in currentDataSource.fields" :key="field" :value="field">
                        {{ field }}
                      </option>
                    </select>
                  </div>
                </div>

                <div class="field-group">
                  <label class="field-label">
                    <span>分组字段</span>
                    <span class="optional">(可选)</span>
                  </label>
                  <div class="select-wrapper">
                    <select v-model="config.groupField" class="field-select" @change="updateChart">
                      <option value="">不分组</option>
                      <option v-for="field in currentDataSource.fields" :key="field" :value="field">
                        {{ field }}
                      </option>
                    </select>
                  </div>
                </div>

                <div class="field-group">
                  <label class="field-label">
                    <span>聚合函数</span>
                  </label>
                  <div class="select-wrapper">
                    <select v-model="config.aggregate" class="field-select" @change="updateChart">
                      <option value="sum">🔢 求和</option>
                      <option value="avg">📊 平均值</option>
                      <option value="count">🔢 计数</option>
                      <option value="max">📈 最大值</option>
                      <option value="min">📉 最小值</option>
                      <option value="none">[LIST] No aggregation</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 多系列配置 -->
          <div v-if="dataSources.length > 0" class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">📊</span>
              <span>多系列配置</span>
              <button class="collapse-btn" @click="toggleSection('multiSeries')">
                {{ collapsedSections.multiSeries ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.multiSeries">
              <div class="series-list">
                <div v-for="(series, sIndex) in config.series" :key="sIndex" class="series-item">
                  <div class="series-header">
                    <input
                      v-model="series.seriesName"
                      type="text"
                      placeholder="系列名称"
                      class="series-name-input"
                      @input="updateChart"
                    />
                    <button
                      class="remove-series-btn"
                      title="删除系列"
                      @click="removeSeries(sIndex)"
                    >
                      <span>✕</span>
                    </button>
                  </div>
                  <div class="series-fields">
                    <div class="series-row">
                      <div class="field-group">
                        <label>数据源</label>
                        <select
                          v-model="series.dataSourceIndex"
                          class="field-select"
                          @change="updateChart"
                        >
                          <option
                            v-for="(source, dIndex) in dataSources"
                            :key="dIndex"
                            :value="dIndex"
                          >
                            {{ source.name }}
                          </option>
                        </select>
                      </div>
                      <div class="field-group">
                        <label>图表类型</label>
                        <select
                          v-model="series.seriesType"
                          class="field-select"
                          @change="updateChart"
                        >
                          <option value="bar">📊 柱状图</option>
                          <option value="line">📈 折线图</option>
                          <option value="area">📊 面积图</option>
                        </select>
                      </div>
                    </div>

                    <div class="series-row">
                      <div class="field-group">
                        <label>Y 轴字段</label>
                        <select v-model="series.yAxis" class="field-select" @change="updateChart">
                          <option value="">请选择</option>
                          <option
                            v-for="field in getSeriesFields(series)"
                            :key="field"
                            :value="field"
                          >
                            {{ field }}
                          </option>
                        </select>
                      </div>
                      <div class="field-group">
                        <label>颜色</label>
                        <div class="color-picker-wrapper">
                          <input
                            v-model="series.color"
                            type="color"
                            class="color-picker"
                            @input="updateChart"
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <button v-if="dataSources.length > 0" class="btn-add-series" @click="addSeries">
                <span>[+]</span>
                <span>添加系列</span>
              </button>
            </div>
          </div>

          <!-- 动画配置 -->
          <div class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">🎬</span>
              <span>动画配置</span>
              <button class="collapse-btn" @click="toggleSection('animationConfig')">
                {{ collapsedSections.animationConfig ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.animationConfig">
              <div class="style-group">
                <label class="style-checkbox-label">
                  <input
                    v-model="config.animation.enabled"
                    type="checkbox"
                    class="style-checkbox"
                    @change="updateChart"
                  />
                  <span>启用动画</span>
                </label>
              </div>

              <div v-if="config.animation.enabled" class="style-group">
                <label class="style-label">动画时长（ms）</label>
                <input
                  v-model.number="config.animation.duration"
                  type="range"
                  min="0"
                  max="5000"
                  step="100"
                  class="style-range"
                  @input="updateChart"
                />
                <span class="range-value">{{ config.animation.duration }}ms</span>
              </div>

              <div v-if="config.animation.enabled" class="style-group">
                <label class="style-label">缓动函数</label>
                <select
                  v-model="config.animation.easing"
                  class="field-select"
                  @change="updateChart"
                >
                  <option value="linear">😐 线性</option>
                  <option value="quadraticIn">📈 二次缓入</option>
                  <option value="quadraticOut">📉 二次缓出</option>
                  <option value="quadraticInOut">📊 二次缓入出</option>
                  <option value="cubicIn">📈 三次缓入</option>
                  <option value="cubicOut">📉 三次缓出</option>
                  <option value="cubicInOut">📊 三次缓入出</option>
                  <option value="quartIn">📈 四次缓入</option>
                  <option value="quartOut">📉 四次缓出</option>
                  <option value="quartInOut">📊 四次缓入出</option>
                  <option value="quinticIn">📈 五次缓入</option>
                  <option value="quinticOut">📉 五次缓出</option>
                  <option value="quinticInOut">📊 五次缓入出</option>
                  <option value="sinusoidalIn">📈 正弦缓入</option>
                  <option value="sinusoidalOut">📉 正弦缓出</option>
                  <option value="sinusoidalInOut">📊 正弦缓入出</option>
                  <option value="exponentialIn">📈 指数缓入</option>
                  <option value="exponentialOut">📉 指数缓出</option>
                  <option value="exponentialInOut">📊 指数缓入出</option>
                  <option value="circularIn">📈 圆形缓入</option>
                  <option value="circularOut">📉 圆形缓出</option>
                  <option value="circularInOut">📊 圆形缓入出</option>
                  <option value="elasticIn">🎽 弹性缓入</option>
                  <option value="elasticOut">🎾 弹性缓出</option>
                  <option value="elasticInOut">🎿 弹性缓入出</option>
                  <option value="backIn">📈 回退缓入</option>
                  <option value="backOut">📉 回退缓出</option>
                  <option value="backInOut">📊 回退缓入出</option>
                  <option value="bounceIn">🏀 弹跳缓入</option>
                  <option value="bounceOut">🏀 弹跳缓出</option>
                  <option value="bounceInOut">🏀 弹跳缓入出</option>
                </select>
              </div>
            </div>
          </div>

          <!-- 图表样式配置 -->
          <div class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">🎨</span>
              <span>样式配置</span>
              <button class="collapse-btn" @click="toggleSection('styleConfig')">
                {{ collapsedSections.styleConfig ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.styleConfig">
              <div class="style-config">
                <div class="style-group">
                  <label class="style-label">图表标题</label>
                  <input
                    v-model="config.title"
                    type="text"
                    placeholder="输入图表标题"
                    class="style-input"
                    @input="updateChart"
                  />
                </div>

                <div
                  v-if="
                    config.chartType !== 'pie' &&
                    config.chartType !== 'radar' &&
                    config.chartType !== 'gauge'
                  "
                  class="style-group"
                >
                  <label class="style-label">X 轴名称</label>
                  <input
                    v-model="config.xAxisName"
                    type="text"
                    placeholder="X 轴名称"
                    class="style-input"
                    @input="updateChart"
                  />
                </div>

                <div
                  v-if="
                    config.chartType !== 'pie' &&
                    config.chartType !== 'radar' &&
                    config.chartType !== 'gauge'
                  "
                  class="style-group"
                >
                  <label class="style-label">Y 轴名称</label>
                  <input
                    v-model="config.yAxisName"
                    type="text"
                    placeholder="Y 轴名称"
                    class="style-input"
                    @input="updateChart"
                  />
                </div>

                <div class="style-group">
                  <label class="style-checkbox-label">
                    <input
                      v-model="config.showLegend"
                      type="checkbox"
                      class="style-checkbox"
                      @change="updateChart"
                    />
                    <span>显示图例</span>
                  </label>
                </div>

                <div v-if="config.showLegend" class="style-group">
                  <label class="style-label">图例位置</label>
                  <select
                    v-model="config.legendConfig.position"
                    class="field-select"
                    @change="updateChart"
                  >
                    <option value="top">⬆️ 顶部</option>
                    <option value="bottom">⬇️ 底部</option>
                    <option value="left">⬅️ 左侧</option>
                    <option value="right">➡️ 右侧</option>
                  </select>
                </div>

                <div v-if="config.showLegend" class="style-group">
                  <label class="style-label">图例方向</label>
                  <select
                    v-model="config.legendConfig.orient"
                    class="field-select"
                    @change="updateChart"
                  >
                    <option value="horizontal">↔️ 水平</option>
                    <option value="vertical">↕️ 垂直</option>
                  </select>
                </div>

                <div v-if="config.showLegend" class="style-group">
                  <label class="style-label">图例图标</label>
                  <select
                    v-model="config.legendConfig.icon"
                    class="field-select"
                    @change="updateChart"
                  >
                    <option value="circle">O Circle</option>
                    <option value="rect">[] Rectangle</option>
                    <option value="roundRect">R Rounded Rect</option>
                    <option value="triangle">Triangle</option>
                    <option value="diamond">Diamond</option>
                    <option value="pin">Pin</option>
                    <option value="arrow">Arrow</option>
                    <option value="none">X None</option>
                  </select>
                </div>

                <div
                  v-if="config.showLegend && config.legendConfig.icon !== 'none'"
                  class="style-group"
                >
                  <label class="style-checkbox-label">
                    <input
                      v-model="config.legendConfig.selector"
                      type="checkbox"
                      class="style-checkbox"
                      @change="updateChart"
                    />
                    <span>启用图例选择</span>
                  </label>
                </div>

                <div class="style-group">
                  <label class="style-checkbox-label">
                    <input
                      v-model="config.showLabel"
                      type="checkbox"
                      class="style-checkbox"
                      @change="updateChart"
                    />
                    <span>显示数据标签</span>
                  </label>
                </div>

                <div class="style-group">
                  <label class="style-checkbox-label">
                    <input
                      v-model="config.dataZoom"
                      type="checkbox"
                      class="style-checkbox"
                      @change="updateChart"
                    />
                    <span>启用数据缩放</span>
                  </label>
                </div>

                <div v-if="config.chartType === 'line'" class="style-group">
                  <label class="style-checkbox-label">
                    <input
                      v-model="config.smooth"
                      type="checkbox"
                      class="style-checkbox"
                      @change="updateChart"
                    />
                    <span>平滑曲线</span>
                  </label>
                </div>

                <div
                  v-if="config.chartType === 'line' || config.chartType === 'area'"
                  class="style-group"
                >
                  <label class="style-label">线条宽度</label>
                  <input
                    v-model.number="config.lineWidth"
                    type="range"
                    min="1"
                    max="10"
                    class="style-range"
                    @input="updateChart"
                  />
                  <span class="range-value">{{ config.lineWidth }}px</span>
                </div>

                <div
                  v-if="
                    config.chartType !== 'pie' &&
                    config.chartType !== 'radar' &&
                    config.chartType !== 'gauge'
                  "
                  class="style-group"
                >
                  <label class="style-label">主色调</label>
                  <div class="color-picker-wrapper">
                    <input
                      v-model="config.color"
                      type="color"
                      class="color-picker"
                      @input="updateChart"
                    />
                  </div>
                </div>

                <div
                  v-if="
                    config.chartType === 'pie' ||
                    config.chartType === 'pie-donut' ||
                    config.chartType === 'pie-rose'
                  "
                  class="style-group"
                >
                  <label class="style-label">饼图半径</label>
                  <input
                    v-model.number="config.pieRadius"
                    type="range"
                    min="20"
                    max="80"
                    class="style-range"
                    @input="updateChart"
                  />
                  <span class="range-value">{{ config.pieRadius }}%</span>
                </div>

                <!-- 高级样式 -->
                <div class="style-divider">高级样式</div>

                <div class="style-group">
                  <label class="style-label">背景样式</label>
                  <div class="background-options">
                    <label class="radio-option">
                      <input
                        v-model="config.backgroundColor"
                        type="radio"
                        value="transparent"
                        @change="updateChart"
                      />
                      <span>透明</span>
                    </label>
                    <label class="radio-option">
                      <input
                        v-model="config.backgroundColor"
                        type="radio"
                        value="#ffffff"
                        @change="updateChart"
                      />
                      <span>白色</span>
                    </label>
                    <label class="radio-option">
                      <input
                        v-model="config.backgroundColor"
                        type="radio"
                        value="#f5f5f5"
                        @change="updateChart"
                      />
                      <span>浅灰</span>
                    </label>
                    <label class="radio-option color-option">
                      自定义
                      <input
                        v-model="config.backgroundGradient"
                        type="color"
                        class="color-picker"
                        @input="updateChart"
                      />
                    </label>
                  </div>
                </div>

                <div
                  v-if="
                    config.chartType !== 'pie' &&
                    config.chartType !== 'radar' &&
                    config.chartType !== 'gauge'
                  "
                  class="style-group"
                >
                  <label class="style-label">边框圆角（px）</label>
                  <input
                    v-model.number="config.borderRadius"
                    type="range"
                    min="0"
                    max="20"
                    class="style-range"
                    @input="updateChart"
                  />
                  <span class="range-value">{{ config.borderRadius }}px</span>
                </div>

                <div class="style-group">
                  <label class="style-label">数据点符号</label>
                  <select v-model="config.symbol" class="field-select" @change="updateChart">
                    <option value="circle">⚪ 圆形</option>
                    <option value="rect">⬜ 矩形</option>
                    <option value="triangle">Triangle</option>
                    <option value="diamond">Diamond</option>
                    <option value="pin">Pin</option>
                    <option value="arrow">Arrow</option>
                    <option value="none">X None</option>
                  </select>
                </div>

                <div class="style-group">
                  <label class="style-label">数据点大小</label>
                  <input
                    v-model.number="config.symbolSize"
                    type="range"
                    min="0"
                    max="20"
                    step="1"
                    class="style-range"
                    @input="updateChart"
                  />
                  <span class="range-value">{{ config.symbolSize }}px</span>
                </div>

                <div class="style-group" style="margin-top: 16px">
                  <label class="style-label">主题颜色</label>
                  <div class="color-palette">
                    <div
                      v-for="color in colorPalette"
                      :key="color"
                      class="color-swatch"
                      :class="{ active: config.color === color }"
                      :style="{ backgroundColor: color }"
                      @click="selectColorTheme(color)"
                    ></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 标记点配置 -->
          <div class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">📍</span>
              <span>标记点</span>
              <button class="collapse-btn" @click="toggleSection('markConfig')">
                {{ collapsedSections.markConfig ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.markConfig">
              <div class="style-group">
                <label class="style-checkbox-label">
                  <input
                    v-model="config.markPoint.enabled"
                    type="checkbox"
                    class="style-checkbox"
                    @change="updateChart"
                  />
                  <span>启用标记点</span>
                </label>
              </div>

              <div v-if="config.markPoint.enabled">
                <div class="style-group">
                  <label class="style-label">标记样式</label>
                  <select
                    v-model="config.markPoint.symbol"
                    class="field-select"
                    @change="updateChart"
                  >
                    <option value="pin">📍 图钉</option>
                    <option value="circle">⚪ 圆形</option>
                    <option value="rect">⬜ 矩形</option>
                    <option value="triangle">🔺 三角形</option>
                    <option value="diamond">🔹 菱形</option>
                    <option value="arrow">➡️ 箭头</option>
                  </select>
                </div>

                <div class="style-group">
                  <label class="style-label">标记大小</label>
                  <input
                    v-model.number="config.markPoint.symbolSize"
                    type="range"
                    min="20"
                    max="100"
                    step="5"
                    class="style-range"
                    @input="updateChart"
                  />
                  <span class="range-value">{{ config.markPoint.symbolSize }}px</span>
                </div>

                <div class="style-divider">标记列表</div>

                <div v-if="config.markPoint.data.length === 0" class="empty-hint">
                  暂无标记点，点击下方按钮添加
                </div>

                <div class="mark-points-list">
                  <div
                    v-for="(mark, index) in config.markPoint.data"
                    :key="index"
                    class="mark-point-item"
                  >
                    <div class="mark-point-row">
                      <label class="mark-label">标记名称</label>
                      <input
                        v-model="mark.name"
                        type="text"
                        class="mark-input"
                        placeholder="标记名称"
                        @input="updateChart"
                      />
                    </div>
                    <div class="mark-point-row">
                      <label class="mark-label">标记值</label>
                      <input
                        v-model.number="mark.value"
                        type="number"
                        class="mark-input"
                        placeholder="标记值"
                        @input="updateChart"
                      />
                    </div>
                    <div class="mark-point-row">
                      <label class="mark-label">X轴位置</label>
                      <input
                        v-model="mark.xAxis"
                        type="text"
                        class="mark-input"
                        placeholder="X轴值"
                        @input="updateChart"
                      />
                    </div>
                    <button
                      class="mark-remove-btn"
                      title="Delete mark"
                      @click="removeMarkPoint(index)"
                    >
                      <span>[DEL]</span>
                    </button>
                  </div>
                </div>

                <button class="btn-add-mark" @click="addMarkPoint">
                  <span>[+]</span>
                  <span>Add Mark</span>
                </button>
              </div>
            </div>
          </div>

          <!-- 趋势线配置 -->
          <div class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">📈</span>
              <span>趋势线</span>
              <button class="collapse-btn" @click="toggleSection('trendConfig')">
                {{ collapsedSections.trendConfig ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.trendConfig">
              <div class="style-group">
                <label class="style-checkbox-label">
                  <input
                    v-model="config.trendLine.enabled"
                    type="checkbox"
                    class="style-checkbox"
                    @change="updateChart"
                  />
                  <span>启用趋势线</span>
                </label>
              </div>

              <div v-if="config.trendLine.enabled">
                <div class="style-group">
                  <label class="style-label">趋势线类型</label>
                  <select
                    v-model="config.trendLine.type"
                    class="field-select"
                    @change="updateChart"
                  >
                    <option value="average">📊 平均值</option>
                    <option value="max">📈 最大值</option>
                    <option value="min">📉 最小值</option>
                    <option value="median">📋 中位数</option>
                    <option value="custom">[EDIT] Custom</option>
                  </select>
                </div>

                <div v-if="config.trendLine.type === 'custom'" class="style-group">
                  <label class="style-label">自定义值</label>
                  <input
                    v-model.number="config.trendLine.customValue"
                    type="number"
                    class="style-input"
                    placeholder="输入自定义值"
                    @input="updateChart"
                  />
                </div>

                <div class="style-group">
                  <label class="style-label">线条样式</label>
                  <select
                    v-model="config.trendLine.lineStyle"
                    class="field-select"
                    @change="updateChart"
                  >
                    <option value="solid">➖ 实线</option>
                    <option value="dashed">┄┄ 虚线</option>
                    <option value="dotted">···· 点线</option>
                  </select>
                </div>

                <div v-if="processedData && processedData.length > 0" class="trend-info">
                  <div class="trend-stat">
                    <span class="trend-label">数据点数:</span>
                    <span class="trend-value">{{ processedData[0]?.data?.length || 0 }}</span>
                  </div>
                  <div class="trend-stat">
                    <span class="trend-label">数据范围:</span>
                    <span class="trend-value">
                      {{ getTrendRange(processedData) }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 多坐标轴配置 -->
          <div v-if="['bar', 'line', 'area'].includes(config.chartType)" class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">📊</span>
              <span>多坐标轴</span>
              <button class="collapse-btn" @click="toggleSection('multiAxis')">
                {{ collapsedSections.multiAxis ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.multiAxis">
              <div class="style-group">
                <label class="style-checkbox-label">
                  <input
                    v-model="config.enableDualAxis"
                    type="checkbox"
                    class="style-checkbox"
                    @change="updateChart"
                  />
                  <span>启用双Y轴</span>
                </label>
              </div>

              <div v-if="config.enableDualAxis">
                <div class="style-group">
                  <label class="style-label">右Y轴名称</label>
                  <input
                    v-model="config.yAxis2Name"
                    type="text"
                    placeholder="右Y轴名称"
                    class="style-input"
                    @input="updateChart"
                  />
                </div>

                <div v-if="config.series && config.series.length > 0" class="style-group">
                  <label class="style-label">系列坐标轴</label>
                  <div class="series-axis-list">
                    <div
                      v-for="(seriesItem, sIndex) in config.series"
                      :key="sIndex"
                      class="series-axis-item"
                    >
                      <span class="axis-series-name">{{
                        seriesItem.seriesName || `系列 ${sIndex + 1}`
                      }}</span>
                      <div class="axis-selector">
                        <label class="axis-option">
                          <input
                            v-model="seriesItem.yAxisIndex"
                            type="radio"
                            :name="`axis-${sIndex}`"
                            :value="0"
                            @change="updateChart"
                          />
                          <span class="axis-label-left">左轴</span>
                        </label>
                        <label class="axis-option">
                          <input
                            v-model="seriesItem.yAxisIndex"
                            type="radio"
                            :name="`axis-${sIndex}`"
                            :value="1"
                            @change="updateChart"
                          />
                          <span class="axis-label-right">右轴</span>
                        </label>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 数据处理配置 -->
          <div v-if="currentDataSource" class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">🔄</span>
              <span>数据处理</span>
              <button class="collapse-btn" @click="toggleSection('dataProcessing')">
                {{ collapsedSections.dataProcessing ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.dataProcessing">
              <div class="style-group">
                <label class="style-checkbox-label">
                  <input
                    v-model="config.dataProcessing.enabled"
                    type="checkbox"
                    class="style-checkbox"
                    @change="updateChart"
                  />
                  <span>启用数据处理</span>
                </label>
              </div>

              <div v-if="config.dataProcessing.enabled">
                <!-- 排序配置 -->
                <div class="style-divider">排序设置</div>

                <div class="style-group">
                  <label class="style-label">排序字段</label>
                  <select
                    v-model="config.dataProcessing.sortBy"
                    class="field-select"
                    @change="updateChart"
                  >
                    <option value="">不排序</option>
                    <option v-for="field in currentDataSource.fields" :key="field" :value="field">
                      {{ field }}
                    </option>
                  </select>
                </div>

                <div v-if="config.dataProcessing.sortBy" class="style-group">
                  <label class="style-label">排序方式</label>
                  <div class="radio-group">
                    <label class="radio-option">
                      <input
                        v-model="config.dataProcessing.sortOrder"
                        type="radio"
                        value="asc"
                        @change="updateChart"
                      />
                      <span>⬆️ 升序</span>
                    </label>
                    <label class="radio-option">
                      <input
                        v-model="config.dataProcessing.sortOrder"
                        type="radio"
                        value="desc"
                        @change="updateChart"
                      />
                      <span>⬇️ 降序</span>
                    </label>
                  </div>
                </div>

                <!-- 过滤配置 -->
                <div class="style-divider">过滤设置</div>

                <div class="style-group">
                  <label class="style-label">过滤字段</label>
                  <select
                    v-model="config.dataProcessing.filterCondition"
                    class="field-select"
                    @change="updateChart"
                  >
                    <option value="">不过滤</option>
                    <option v-for="field in currentDataSource.fields" :key="field" :value="field">
                      {{ field }}
                    </option>
                  </select>
                </div>

                <div v-if="config.dataProcessing.filterCondition" class="style-group">
                  <label class="style-label">过滤值</label>
                  <input
                    v-model="config.dataProcessing.filterValue"
                    type="text"
                    placeholder="输入过滤值（支持多个，逗号分隔）"
                    class="style-input"
                    @input="updateChart"
                  />
                </div>

                <!-- Top N配置 -->
                <div class="style-divider">Top N 设置</div>

                <div class="style-group">
                  <label class="style-label">显示前 N 项</label>
                  <input
                    v-model.number="config.dataProcessing.topN"
                    type="number"
                    min="0"
                    placeholder="0 表示显示全部"
                    class="style-input"
                    @input="updateChart"
                  />
                  <span class="field-hint">设置为 0 显示所有数据</span>
                </div>

                <!-- 数据预览 -->
                <div class="style-divider" style="margin-top: 16px">数据预览</div>
                <div class="data-preview-info">
                  <div class="preview-stat">
                    <span class="preview-label">原始数据:</span>
                    <span class="preview-value">{{ currentDataSource?.data?.length || 0 }} 条</span>
                  </div>
                  <div class="preview-stat">
                    <span class="preview-label">处理后数据:</span>
                    <span class="preview-value">{{ filteredDataCount || 0 }} 条</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 模板管理 -->
          <div class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">📋</span>
              <span>模板管理</span>
              <button class="collapse-btn" @click="toggleSection('templateConfig')">
                {{ collapsedSections.templateConfig ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.templateConfig">
              <!-- 保存模板 -->
              <div class="style-group">
                <label class="style-label">保存当前配置为模板</label>
                <div class="template-save-row">
                  <input
                    v-model="templateName"
                    type="text"
                    placeholder="输入模板名称"
                    class="style-input"
                    style="flex: 1"
                  />
                  <button class="btn-save-template" @click="saveTemplate">
                    <span>[SAVE]</span>
                    <span>Save</span>
                  </button>
                </div>
              </div>

              <!-- 模板列表 -->
              <div v-if="templates.length > 0" class="style-divider">已保存的模板</div>

              <div v-if="templates.length > 0" class="templates-list">
                <div
                  v-for="(template, index) in templates"
                  :key="template.id"
                  class="template-item"
                  :class="{ active: selectedTemplate?.id === template.id }"
                >
                  <div class="template-info" @click="loadTemplate(template)">
                    <span class="template-icon">📊</span>
                    <div class="template-details">
                      <span class="template-name">{{ template.name }}</span>
                      <span class="template-meta"
                        >{{ template.chartType }} ·
                        {{ new Date(template.createdAt).toLocaleDateString() }}</span
                      >
                    </div>
                  </div>
                  <div class="template-actions">
                    <button
                      class="template-action-btn apply-btn"
                      title="Apply template"
                      @click="applyTemplate(template)"
                    >
                      <span>[OK]</span>
                    </button>
                    <button
                      class="template-action-btn delete-btn"
                      title="Delete template"
                      @click.stop="deleteTemplate(index)"
                    >
                      <span>[DEL]</span>
                    </button>
                  </div>
                </div>
              </div>

              <!-- Empty state -->
              <div v-if="templates.length === 0" class="empty-templates">
                <span class="empty-icon">[LIST]</span>
                <p>No saved templates</p>
                <p class="empty-hint">Save common configs for quick apply</p>
              </div>

              <!-- 批量操作 -->
              <div v-if="templates.length > 0" class="style-divider">批量操作</div>
              <div v-if="templates.length > 0" class="template-batch-actions">
                <button class="btn-batch" title="导出所有模板" @click="exportAllTemplates">
                  <span>📤</span>
                  <span>导出模板</span>
                </button>
                <button class="btn-batch" title="导入模板" @click="importTemplates">
                  <span>[IMPORT]</span>
                  <span>Import Template</span>
                </button>
                <button
                  class="btn-batch btn-batch-danger"
                  title="Clear all templates"
                  @click="clearAllTemplates"
                >
                  <span>[DEL]</span>
                  <span>Clear All</span>
                </button>
              </div>
            </div>
          </div>

          <!-- 主题配置 -->
          <div class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">🎨</span>
              <span>主题系统</span>
              <button class="collapse-btn" @click="toggleSection('themeConfig')">
                {{ collapsedSections.themeConfig ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.themeConfig">
              <!-- 预设主题 -->
              <div class="style-group">
                <label class="style-label">预设主题</label>
                <div class="theme-presets-grid">
                  <div
                    v-for="preset in themePresets"
                    :key="preset.id"
                    class="theme-preset-card"
                    :class="{ active: currentTheme === preset.id }"
                    @click="applyTheme(preset)"
                  >
                    <span class="theme-preset-icon">{{ preset.icon }}</span>
                    <span class="theme-preset-name">{{ preset.name }}</span>
                    <div v-if="preset.id !== 'custom'" class="theme-preset-colors">
                      <span
                        class="theme-color-dot"
                        :style="{ backgroundColor: preset.colors.primaryColor }"
                      ></span>
                      <span
                        class="theme-color-dot"
                        :style="{ backgroundColor: preset.colors.backgroundColor }"
                      ></span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 自定义主题 -->
              <div v-if="currentTheme === 'custom'" class="style-divider">自定义主题</div>

              <div v-if="currentTheme === 'custom'" class="custom-theme-panel">
                <div class="style-group">
                  <label class="style-label">背景颜色</label>
                  <div class="color-input-row">
                    <input
                      v-model="customTheme.backgroundColor"
                      type="color"
                      class="color-picker-large"
                      @input="applyCustomTheme"
                    />
                    <input
                      v-model="customTheme.backgroundColor"
                      type="text"
                      class="style-input color-hex-input"
                      placeholder="#ffffff"
                      @input="applyCustomTheme"
                    />
                  </div>
                </div>

                <div class="style-group">
                  <label class="style-label">文字颜色</label>
                  <div class="color-input-row">
                    <input
                      v-model="customTheme.textColor"
                      type="color"
                      class="color-picker-large"
                      @input="applyCustomTheme"
                    />
                    <input
                      v-model="customTheme.textColor"
                      type="text"
                      class="style-input color-hex-input"
                      placeholder="#1f2937"
                      @input="applyCustomTheme"
                    />
                  </div>
                </div>

                <div class="style-group">
                  <label class="style-label">主色调</label>
                  <div class="color-input-row">
                    <input
                      v-model="customTheme.primaryColor"
                      type="color"
                      class="color-picker-large"
                      @input="applyCustomTheme"
                    />
                    <input
                      v-model="customTheme.primaryColor"
                      type="text"
                      class="style-input color-hex-input"
                      placeholder="#3b82f6"
                      @input="applyCustomTheme"
                    />
                  </div>
                </div>

                <div class="style-group">
                  <label class="style-label">边框颜色</label>
                  <div class="color-input-row">
                    <input
                      v-model="customTheme.borderColor"
                      type="color"
                      class="color-picker-large"
                      @input="applyCustomTheme"
                    />
                    <input
                      v-model="customTheme.borderColor"
                      type="text"
                      class="style-input color-hex-input"
                      placeholder="#e5e7eb"
                      @input="applyCustomTheme"
                    />
                  </div>
                </div>

                <div class="style-group">
                  <label class="style-label">网格颜色</label>
                  <div class="color-input-row">
                    <input
                      v-model="customTheme.gridColor"
                      type="color"
                      class="color-picker-large"
                      @input="applyCustomTheme"
                    />
                    <input
                      v-model="customTheme.gridColor"
                      type="text"
                      class="style-input color-hex-input"
                      placeholder="#e5e7eb"
                      @input="applyCustomTheme"
                    />
                  </div>
                </div>
              </div>

              <!-- 主题预览 -->
              <div class="style-divider">主题预览</div>
              <div class="theme-preview-box" :style="getThemePreviewStyle()">
                <div class="theme-preview-chart">
                  <div class="theme-preview-title">图表标题</div>
                  <div class="theme-preview-content">
                    <div
                      class="theme-preview-bar"
                      style="width: 60%"
                      :style="{ backgroundColor: themePreviewBarColor }"
                    ></div>
                    <div
                      class="theme-preview-bar"
                      style="width: 80%"
                      :style="{ backgroundColor: themePreviewBarColor }"
                    ></div>
                    <div
                      class="theme-preview-bar"
                      style="width: 45%"
                      :style="{ backgroundColor: themePreviewBarColor }"
                    ></div>
                    <div
                      class="theme-preview-bar"
                      style="width: 70%"
                      :style="{ backgroundColor: themePreviewBarColor }"
                    ></div>
                  </div>
                </div>
              </div>

              <!-- 主题操作 -->
              <div class="style-divider">主题管理</div>
              <div class="theme-actions">
                <button class="btn-theme-action" title="导出当前主题" @click="exportTheme">
                  <span>📤</span>
                  <span>导出主题</span>
                </button>
                <button class="btn-theme-action" title="导入主题" @click="importTheme">
                  <span>📥</span>
                  <span>导入主题</span>
                </button>
                <button class="btn-theme-action" title="重置为默认主题" @click="resetTheme">
                  <span>🔄</span>
                  <span>重置主题</span>
                </button>
              </div>
            </div>
          </div>

          <!-- 批量操作 -->
          <div v-if="charts.length > 0" class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">⚡</span>
              <span>批量操作</span>
              <button class="collapse-btn" @click="toggleSection('batchConfig')">
                {{ collapsedSections.batchConfig ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.batchConfig">
              <div class="style-group">
                <label class="style-label">批量编辑样式</label>
                <div class="color-input-row">
                  <input v-model="batchColor" type="color" class="color-picker-large" />
                  <input
                    v-model="batchColor"
                    type="text"
                    class="style-input color-hex-input"
                    placeholder="#3b82f6"
                  />
                  <button class="btn-batch-apply" @click="applyBatchColor">
                    <span>🎨</span>
                    <span>应用颜色</span>
                  </button>
                </div>
              </div>

              <div class="style-group">
                <label class="style-label">批量设置图例</label>
                <div class="batch-toggle-row">
                  <label class="style-checkbox-label">
                    <input v-model="batchEnableLegend" type="checkbox" class="style-checkbox" />
                    <span>显示图例</span>
                  </label>
                  <button class="btn-batch-apply" @click="applyBatchLegend">
                    <span>📊</span>
                    <span>应用设置</span>
                  </button>
                </div>
              </div>

              <div class="style-group">
                <label class="style-label">批量设置标签</label>
                <div class="batch-toggle-row">
                  <label class="style-checkbox-label">
                    <input v-model="batchEnableLabels" type="checkbox" class="style-checkbox" />
                    <span>显示数据标签</span>
                  </label>
                  <button class="btn-batch-apply" @click="applyBatchLabels">
                    <span>🏷️</span>
                    <span>应用设置</span>
                  </button>
                </div>
              </div>

              <div class="style-divider">批量布局</div>

              <div class="style-group">
                <label class="style-label">统一图表大小</label>
                <div class="batch-size-row">
                  <div class="batch-size-group">
                    <label class="batch-size-label">宽度</label>
                    <input
                      v-model.number="config.width"
                      type="number"
                      min="300"
                      max="1200"
                      class="style-input size-input"
                      placeholder="500"
                    />
                    <span class="batch-size-unit">px</span>
                  </div>
                  <div class="batch-size-group">
                    <label class="batch-size-label">高度</label>
                    <input
                      v-model.number="config.height"
                      type="number"
                      min="200"
                      max="800"
                      class="style-input size-input"
                      placeholder="400"
                    />
                    <span class="batch-size-unit">px</span>
                  </div>
                  <button class="btn-batch-apply" @click="applyBatchSize">
                    <span>📐</span>
                    <span>统一尺寸</span>
                  </button>
                </div>
              </div>

              <div class="style-group">
                <label class="style-label">网格布局</label>
                <div class="batch-grid-options">
                  <button
                    class="batch-grid-btn"
                    :class="{ active: batchOperation === '2x2' }"
                    @click="arrangeInGrid(2, 2)"
                  >
                    <span>2×2</span>
                  </button>
                  <button
                    class="batch-grid-btn"
                    :class="{ active: batchOperation === '2x3' }"
                    @click="arrangeInGrid(2, 3)"
                  >
                    <span>2×3</span>
                  </button>
                  <button
                    class="batch-grid-btn"
                    :class="{ active: batchOperation === '3x3' }"
                    @click="arrangeInGrid(3, 3)"
                  >
                    <span>3×3</span>
                  </button>
                  <button
                    class="batch-grid-btn"
                    :class="{ active: batchOperation === 'auto' }"
                    @click="autoArrange"
                  >
                    <span>🔄 自动排列</span>
                  </button>
                </div>
              </div>

              <div class="style-divider">批量导出</div>

              <div class="batch-export-actions">
                <button class="btn-batch-export" @click="batchExportImages">
                  <span>[IMG]</span>
                  <span>Export All Images</span>
                </button>
                <button class="btn-batch-export" @click="batchExportPDF">
                  <span>[PDF]</span>
                  <span>Export as PDF</span>
                </button>
                <button class="btn-batch-export" @click="batchExportZIP">
                  <span>[ZIP]</span>
                  <span>Export ZIP</span>
                </button>
              </div>
            </div>
          </div>

          <!-- 智能推荐 -->
          <div v-if="currentDataSource" class="panel-section">
            <h3 class="section-title">
              <span class="title-icon">🤖</span>
              <span>智能推荐</span>
              <button class="collapse-btn" @click="toggleSection('smartConfig')">
                {{ collapsedSections.smartConfig ? '▶' : '▼' }}
              </button>
            </h3>
            <div v-show="!collapsedSections.smartConfig">
              <button class="btn-analyze" @click="analyzeDataAndRecommend">
                <span>🔍</span>
                <span>分析数据并生成推荐</span>
              </button>

              <!-- 推荐结果 -->
              <div v-if="recommendations.length > 0" class="recommendations-container">
                <div class="style-divider" style="margin-top: 16px">数据类型分析</div>
                <div v-if="analysisResult" class="analysis-result">
                  <div class="analysis-item">
                    <span class="analysis-label">数据字段数:</span>
                    <span class="analysis-value">{{ analysisResult.fieldCount }}</span>
                  </div>
                  <div class="analysis-item">
                    <span class="analysis-label">数据记录数:</span>
                    <span class="analysis-value">{{ analysisResult.rowCount }}</span>
                  </div>
                  <div class="analysis-item">
                    <span class="analysis-label">数值字段:</span>
                    <span class="analysis-value">{{
                      analysisResult.numericFields.join(', ') || '无'
                    }}</span>
                  </div>
                  <div class="analysis-item">
                    <span class="analysis-label">分类字段:</span>
                    <span class="analysis-value">{{
                      analysisResult.categoricalFields.join(', ') || '无'
                    }}</span>
                  </div>
                  <div class="analysis-item">
                    <span class="analysis-label">数据质量:</span>
                    <span
                      class="analysis-value"
                      :class="{
                        good: analysisResult.quality === '优秀',
                        medium: analysisResult.quality === '良好',
                        poor: analysisResult.quality === '一般'
                      }"
                    >
                      {{ analysisResult.quality }}
                    </span>
                  </div>
                </div>

                <div class="style-divider" style="margin-top: 16px">推荐的图表类型</div>
                <div class="recommendations-list">
                  <div
                    v-for="(rec, index) in recommendations"
                    :key="index"
                    class="recommendation-card"
                    @click="applyRecommendation(rec)"
                  >
                    <div class="rec-header">
                      <span class="rec-icon">{{ rec.icon }}</span>
                      <div class="rec-title-group">
                        <span class="rec-title">{{ rec.chartType }}</span>
                        <span class="rec-score">匹配度: {{ rec.score }}%</span>
                      </div>
                      <span class="rec-priority" :class="'priority-' + rec.priority">{{
                        rec.priority
                      }}</span>
                    </div>
                    <p class="rec-reason">{{ rec.reason }}</p>
                    <div v-if="rec.config" class="rec-config">
                      <span class="rec-config-title">推荐配置:</span>
                      <div class="rec-config-items">
                        <span v-for="(value, key) in rec.config" :key="key" class="rec-config-item">
                          {{ formatConfigKey(key) }}: <strong>{{ value }}</strong>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <button class="btn-apply-top-rec" @click="applyTopRecommendation">
                  <span>✨</span>
                  <span>应用最佳推荐</span>
                </button>
              </div>

              <!-- 无数据提示 -->
              <div v-if="!currentDataSource || !analysisResult" class="smart-empty">
                <span class="empty-icon">📊</span>
                <p>请先导入数据源，然后点击上方按钮分析</p>
                <p class="empty-hint">系统将根据数据特征智能推荐合适的图表类型</p>
              </div>
            </div>
          </div>
        </div>

        <!-- 右侧图表展示区 -->
        <div class="chart-display-area">
          <!-- 多图表容器 -->
          <div
            v-for="(chartItem, index) in charts"
            :key="chartItem.id"
            class="chart-wrapper"
            :class="{ active: selectedChartIndex === index }"
            :style="getChartStyle(chartItem)"
          >
            <div :ref="el => setChartRef(el, index)" class="chart-dom"></div>

            <!-- 图表操作栏 -->
            <div class="chart-actions" @mousedown.stop>
              <button
                class="action-btn"
                :class="{ active: selectedChartIndex === index }"
                title="选中图表"
                @click="selectChart(index)"
              >
                📊
              </button>
              <button class="action-btn" title="复制图表" @click="duplicateChart(index)">📋</button>
              <button
                class="action-btn delete-btn"
                title="Delete chart"
                @click="deleteChart(index)"
              >
                [DEL]
              </button>
            </div>

            <!-- 图表拖拽手柄 -->
            <div class="drag-handle" title="拖拽移动" @mousedown.stop="startDrag($event, index)">
              <span class="drag-icon">⋮⋮</span>
            </div>
            <div
              class="resize-handle"
              title="调整大小"
              @mousedown.stop="startResize($event, index)"
            >
              <span class="resize-icon">⤡</span>
            </div>
          </div>

          <!-- Empty state -->
          <div v-if="charts.length === 0" class="empty-state">
            <div class="empty-icon">[CHART]</div>
            <p class="empty-title">Canvas is empty</p>
            <p class="empty-hint">Click "[+] Add chart" at bottom left to start</p>
            <button class="empty-action-btn" @click="addNewChart">
              <span>[+]</span>
              <span>Create Now</span>
            </button>
          </div>
          <div v-else-if="!currentDataSource && dataSources.length === 0" class="empty-state">
            <div class="empty-icon">[DIR]</div>
            <p class="empty-title">Please import a data file first</p>
            <p class="empty-hint">Supports drag & drop or upload .xlsx, .csv, .json files</p>
          </div>
          <div v-else-if="!currentDataSource" class="empty-state">
            <div class="empty-icon">📋</div>
            <p class="empty-title">请选择数据源</p>
          </div>
        </div>
      </div>

      <!-- Footer action bar -->
      <div class="editor-footer">
        <div class="footer-left">
          <button class="btn btn-primary" @click="addNewChart">
            <span>[+]</span>
            <span>Add Chart</span>
          </button>
          <button class="btn btn-secondary" @click="clearAll">
            <span>[RESET]</span>
            <span>Clear Canvas</span>
          </button>
        </div>

        <div class="footer-right">
          <div class="export-group">
            <button class="btn btn-export" @click="showExportMenu = !showExportMenu">
              <span>📤</span>
              <span>导出</span>
            </button>
            <div v-if="showExportMenu" class="export-menu">
              <button class="export-option" @click="exportSingleImage">
                <span class="option-icon">📷</span>
                <span>导出当前图表</span>
              </button>
              <button class="export-option" @click="exportAllImages">
                <span class="option-icon">[IMG]</span>
                <span>Export All Charts</span>
              </button>
              <button class="export-option" @click="exportHTML">
                <span class="option-icon">[HTML]</span>
                <span>Export as HTML</span>
              </button>
              <button class="export-option" @click="exportConfig">
                <span class="option-icon">[CONFIG]</span>
                <span>Export Config JSON</span>
              </button>
            </div>
          </div>
          <button class="btn btn-close" @click="closeEditor">
            <span>关闭</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 帮助弹窗 -->
    <div v-if="showHelp" class="help-modal" @click.self="showHelp = false">
      <div class="help-content">
        <div class="help-header">
          <h3>使用帮助</h3>
          <button class="close-btn" @click="showHelp = false">✕</button>
        </div>
        <div class="help-body">
          <div class="help-section">
            <h4>📁 数据导入</h4>
            <p>支持拖拽或点击上传 .xlsx, .xls, .csv, .json 格式的数据文件</p>
          </div>
          <div class="help-section">
            <h4>📊 图表类型</h4>
            <ul>
              <li>柱状图: 用于比较分类数据</li>
              <li>折线图: 用于展示趋势变化</li>
              <li>面积图: 强调累积效果</li>
              <li>散点图: 用于分析数据相关性</li>
              <li>饼图: 显示部分与整体关系</li>
              <li>雷达图: 多维度数据对比</li>
              <li>漏斗图: 展示数据流向</li>
              <li>仪表盘: 显示单个数值进度</li>
            </ul>
          </div>
          <div class="help-section">
            <h4>🎨 样式配置</h4>
            <p>可以调整图表标题、坐标轴名称、颜色、平滑度等多项样式设置</p>
          </div>
          <div class="help-section">
            <h4>📤 导出功能</h4>
            <p>支持导出为图片、HTML 或配置 JSON 文件</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
  import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
  import * as echarts from 'echarts'
  import {
    LineChart,
    BarChart,
    PieChart,
    ScatterChart,
    RadarChart,
    GaugeChart
  } from 'echarts/charts'
  import {
    GridComponent,
    TitleComponent,
    TooltipComponent,
    LegendComponent,
    ToolboxComponent,
    DataZoomComponent
  } from 'echarts/components'
  import { CanvasRenderer } from 'echarts/renderers'

  // 注册必需的组件
  echarts.use([
    GridComponent,
    TitleComponent,
    TooltipComponent,
    LegendComponent,
    ToolboxComponent,
    DataZoomComponent,
    LineChart,
    BarChart,
    PieChart,
    ScatterChart,
    RadarChart,
    GaugeChart,
    CanvasRenderer
  ])

  import * as XLSX from 'xlsx'

  // Props
  const props = defineProps({
    visible: {
      type: Boolean,
      default: false
    }
  })

  // Emits
  const emit = defineEmits(['close'])

  // Refs
  const chartDoms = ref([])
  const fileInput = ref(null)
  const showExportMenu = ref(false)
  const showHelp = ref(false)
  const chartInstances = ref({})

  // 主题切换
  const isDarkTheme = ref(false)

  // 折叠状态
  const collapsedSections = ref({
    dataImport: false,
    chartType: false,
    dataConfig: false,
    multiSeries: false,
    animationConfig: false,
    styleConfig: false,
    markConfig: false,
    multiAxis: false,
    dataProcessing: false,
    templateConfig: false,
    themeConfig: false,
    batchConfig: false,
    smartConfig: false
  })

  // 批量操作
  const batchOperation = ref('')
  const batchColor = ref('#3b82f6')
  const batchEnableLegend = ref(true)
  const batchEnableLabels = ref(true)
  const selectedChartsForBatch = ref([])

  // 智能推荐
  const recommendations = ref([])
  const analysisResult = ref(null)
  const showRecommendations = ref(false)

  // 主题管理
  const currentTheme = ref('light')
  const customTheme = ref({
    backgroundColor: '#ffffff',
    textColor: '#1f2937',
    primaryColor: '#3b82f6',
    borderColor: '#e5e7eb',
    gridColor: '#e5e7eb'
  })

  const themePresets = [
    {
      id: 'light',
      name: '明亮',
      icon: '[SUN]',
      colors: {
        backgroundColor: '#ffffff',
        textColor: '#1f2937',
        primaryColor: '#3b82f6',
        borderColor: '#e5e7eb',
        gridColor: '#e5e7eb'
      }
    },
    {
      id: 'dark',
      name: '深色',
      icon: '[MOON]',
      colors: {
        backgroundColor: '#1f2937',
        textColor: '#f9fafb',
        primaryColor: '#60a5fa',
        borderColor: '#374151',
        gridColor: '#374151'
      }
    },
    {
      id: 'blue',
      name: '蓝色',
      icon: '🔵',
      colors: {
        backgroundColor: '#eff6ff',
        textColor: '#1e3a8a',
        primaryColor: '#2563eb',
        borderColor: '#bfdbfe',
        gridColor: '#dbeafe'
      }
    },
    {
      id: 'green',
      name: '绿色',
      icon: '🟢',
      colors: {
        backgroundColor: '#ecfdf5',
        textColor: '#064e3b',
        primaryColor: '#059669',
        borderColor: '#a7f3d0',
        gridColor: '#d1fae5'
      }
    },
    {
      id: 'custom',
      name: '自定义',
      icon: '🎨',
      colors: customTheme.value
    }
  ]

  // 模板管理
  const templates = ref([])
  const selectedTemplate = ref(null)
  const templateName = ref('')

  // 数据
  const dataSources = ref([])
  const selectedDataSourceIndex = ref(null)
  const selectedChartIndex = ref(0)
  let chartIdCounter = 0

  // 图表配置数组
  const charts = ref([])

  // 颜色调色板
  const colorPalette = [
    '#3b82f6', // 蓝
    '#10b981', // 绿
    '#f59e0b', // 橙
    '#ef4444', // 红
    '#8b5cf6', // 紫
    '#ec4899', // 粉
    '#06b6d4', // 青
    '#f97316' // 深橙
  ]

  // 图表类型选项
  const chartTypes = [
    // 基础图表
    { value: 'bar', label: '柱状图', icon: '📊', category: 'basic' },
    { value: 'line', label: '折线图', icon: '📈', category: 'basic' },
    { value: 'area', label: '面积图', icon: '📊', category: 'basic' },
    { value: 'scatter', label: '散点图', icon: '⚡', category: 'basic' },
    { value: 'pie', label: '饼图', icon: '🥧', category: 'basic' },
    { value: 'radar', label: '雷达图', icon: '🎯', category: 'basic' },
    { value: 'funnel', label: '漏斗图', icon: '📉', category: 'basic' },
    { value: 'gauge', label: '仪表盘', icon: '⏱️', category: 'basic' },

    // 柱状图变体
    { value: 'bar-stack', label: '堆叠柱状图', icon: '📊', category: 'stack' },
    { value: 'bar-group', label: '分组柱状图', icon: '📊', category: 'group' },
    { value: 'bar-percent', label: '百分比堆叠柱状图', icon: '📊', category: 'percent' },

    // 折线图变体
    { value: 'line-step', label: '阶梯线图', icon: '📈', category: 'step' },
    { value: 'area-step', label: '阶梯面积图', icon: '📊', category: 'step' },

    // 饼图变体
    { value: 'pie-donut', label: '环形图', icon: '🍩', category: 'variant' },
    { value: 'pie-rose', label: '南丁格尔玫瑰图', icon: '🌹', category: 'rose' },
    { value: 'pie-double', label: '双饼图', icon: '🥧', category: 'variant' },

    // 高级图表
    { value: 'boxplot', label: 'Box Plot', icon: '[BOX]', category: 'advanced' },
    { value: 'heatmap', label: '热力图', icon: '🔥', category: 'advanced' },
    { value: 'sankey', label: '桑基图', icon: '🌊', category: 'advanced' },
    { value: 'chord', label: '和弦图', icon: '🎻', category: 'advanced' },
    { value: 'tree', label: '树图', icon: '🌳', category: 'advanced' },
    { value: 'treemap', label: '矩形树图', icon: '🎴', category: 'advanced' },
    { value: 'sunburst', label: 'Sunburst', icon: '[SUN]', category: 'advanced' },
    { value: 'gantt', label: '甘特图', icon: '📅', category: 'advanced' },
    { value: 'funnel-compare', label: '对比漏斗图', icon: '📉', category: 'advanced' }
  ]

  // 当前选中图表的配置
  const config = ref({
    chartType: 'bar',
    title: '',
    xAxis: '',
    yAxis: '',
    xAxisName: '',
    yAxisName: '',
    showLegend: true,
    showLabel: false,
    dataZoom: false,
    smooth: true,
    lineWidth: 2,
    pieRadius: 60,
    width: 500,
    height: 400,
    x: 50,
    y: 50,
    color: '#3b82f6',
    series: [],
    // 动画配置
    animation: {
      enabled: true,
      duration: 1000,
      easing: 'cubicOut'
    },
    // 基础样式增强
    backgroundColor: 'transparent',
    borderRadius: 0,
    borderWidth: 0,
    borderColor: '#e5e7eb',
    symbolSize: 6,
    symbol: 'circle',
    // 高级样式
    backgroundGradient: null,
    // 标记点
    markPoint: {
      enabled: false,
      data: [],
      symbol: 'pin',
      symbolSize: 50,
      label: {
        show: true
      }
    },
    // 趋势线
    trendLine: {
      enabled: false,
      data: [],
      type: 'average',
      lineStyle: 'solid',
      customValue: 0
    },
    // 多坐标轴配置
    yAxisIndex: 0,
    enableDualAxis: false,
    yAxis2Name: '',
    yAxis2: '',
    seriesAxisIndex: [],
    // 图例配置
    legendConfig: {
      position: 'bottom',
      orient: 'horizontal',
      show: true,
      icon: 'circle',
      selector: false,
      data: []
    },
    // 数据处理配置
    dataProcessing: {
      enabled: false,
      sortBy: '',
      sortOrder: 'asc',
      filterCondition: '',
      filterValue: '',
      topN: 0
    }
  })

  // 系列默认配置模板
  const defaultSeriesConfig = {
    dataSourceIndex: 0,
    yAxis: '',
    seriesType: 'bar',
    seriesName: '',
    color: '#3b82f6',
    groupField: '',
    aggregate: 'sum'
  }

  // 计算属性
  const currentDataSource = computed(() => {
    if (
      selectedDataSourceIndex.value === null ||
      selectedDataSourceIndex.value >= dataSources.value.length
    ) {
      return null
    }
    return dataSources.value[selectedDataSourceIndex.value]
  })

  const chartStyle = computed(() => ({
    width: `${config.value.width}px`,
    height: `${config.value.height}px`,
    left: `${config.value.x}px`,
    top: `${config.value.y}px`,
    position: 'absolute'
  }))

  // 计算处理后的数据量
  const filteredDataCount = computed(() => {
    if (!currentDataSource.value || !config.value.dataProcessing.enabled) {
      return currentDataSource.value?.data?.length || 0
    }

    const { sortBy, sortOrder, filterCondition, filterValue, topN } = config.value.dataProcessing
    let data = [...(currentDataSource.value.data || [])]

    // 过滤
    if (filterCondition && filterValue) {
      const filterValues = filterValue.split(',').map(v => v.trim().toLowerCase())
      data = data.filter(row => {
        const rowValue = String(row[filterCondition] || '').toLowerCase()
        return filterValues.some(fv => rowValue.includes(fv))
      })
    }

    // 排序
    if (sortBy) {
      data.sort((a, b) => {
        const aVal = a[sortBy]
        const bVal = b[sortBy]

        if (typeof aVal === 'number' && typeof bVal === 'number') {
          return sortOrder === 'asc' ? aVal - bVal : bVal - aVal
        }

        const aStr = String(aVal || '').toLowerCase()
        const bStr = String(bVal || '').toLowerCase()

        return sortOrder === 'asc' ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr)
      })
    }

    // Top N
    if (topN > 0) {
      data = data.slice(0, topN)
    }

    return data.length
  })

  // 切换面板折叠
  const toggleSection = section => {
    collapsedSections.value[section] = !collapsedSections.value[section]
  }

  // 切换主题
  const toggleTheme = () => {
    isDarkTheme.value = !isDarkTheme.value
  }

  // 选择图表类型
  const selectChartType = type => {
    config.value.chartType = type
    updateChart()
  }

  // 选择颜色主题
  const selectColorTheme = color => {
    config.value.color = color
    updateChart()
  }

  // 文件处理
  const handleUploadClick = () => {
    if (fileInput.value) {
      fileInput.value.click()
    }
  }

  const handleFileDrop = async event => {
    const files = event.dataTransfer.files
    await processFiles(files)
  }

  const handleFileSelect = async event => {
    const files = event.target.files
    await processFiles(files)
    // 重置input值，允许重新选择同一个文件
    if (event.target) {
      event.target.value = ''
    }
  }

  const processFiles = async files => {
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      try {
        let data
        if (file.name.endsWith('.json')) {
          data = await readJsonFile(file)
        } else {
          data = await readExcelFile(file)
        }
        dataSources.value.push({
          name: file.name,
          data: data,
          fields: Object.keys(data[0] || {})
        })

        if (selectedDataSourceIndex.value === null) {
          selectedDataSourceIndex.value = 0
        }
      } catch (error) {
        alert(`文件 "${file.name}" 解析失败，请检查文件格式`)
      }
    }
  }

  const readExcelFile = file => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = e => {
        try {
          const data = e.target.result
          const workbook = XLSX.read(data, { type: 'array' })
          const firstSheetName = workbook.SheetNames[0]
          const worksheet = workbook.Sheets[firstSheetName]
          const jsonData = XLSX.utils.sheet_to_json(worksheet)
          resolve(jsonData)
        } catch (err) {
          reject(err)
        }
      }
      reader.onerror = reject
      reader.readAsArrayBuffer(file)
    })
  }

  const readJsonFile = file => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = e => {
        try {
          const data = JSON.parse(e.target.result)
          resolve(Array.isArray(data) ? data : [data])
        } catch (err) {
          reject(err)
        }
      }
      reader.onerror = reject
      reader.readAsText(file)
    })
  }

  const removeDataSource = index => {
    dataSources.value.splice(index, 1)
    if (selectedDataSourceIndex.value === index) {
      selectedDataSourceIndex.value = dataSources.value.length > 0 ? 0 : null
    } else if (selectedDataSourceIndex.value > index) {
      selectedDataSourceIndex.value--
    }
  }

  const selectDataSource = index => {
    selectedDataSourceIndex.value = index
    config.value.xAxis = ''
    config.value.yAxis = ''
    config.value.groupField = ''
  }

  // 系列管理
  const addSeries = () => {
    const newSeries = {
      ...defaultSeriesConfig,
      seriesName: `系列 ${config.value.series.length + 1}`,
      dataSourceIndex: selectedDataSourceIndex.value !== null ? selectedDataSourceIndex.value : 0,
      color: colorPalette[config.value.series.length % colorPalette.length]
    }
    config.value.series.push(newSeries)
    updateChart()
  }

  const removeSeries = index => {
    config.value.series.splice(index, 1)
    updateChart()
  }

  const getSeriesFields = series => {
    const dataSource = dataSources.value[series.dataSourceIndex]
    if (!dataSource) return []
    return dataSource.fields || []
  }

  // 标记点管理
  const addMarkPoint = () => {
    config.value.markPoint.data.push({
      name: `标记 ${config.value.markPoint.data.length + 1}`,
      value: 0
    })
    updateChart()
  }

  const removeMarkPoint = index => {
    config.value.markPoint.data.splice(index, 1)
    updateChart()
  }

  // 趋势线计算
  const calculateTrendLine = (data, type) => {
    if (!data || data.length === 0) return []

    const values = data.map(item => parseFloat(item.value) || 0)

    switch (type) {
      case 'average':
        const avg = values.reduce((sum, val) => sum + val, 0) / values.length
        return Array(values.length).fill(avg)
      case 'max':
        const max = Math.max(...values)
        return Array(values.length).fill(max)
      case 'min':
        const min = Math.min(...values)
        return Array(values.length).fill(min)
      case 'median':
        const sorted = [...values].sort((a, b) => a - b)
        const mid = Math.floor(sorted.length / 2)
        const median = sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
        return Array(values.length).fill(median)
      case 'custom':
        return Array(values.length).fill(config.value.trendLine.customValue || 0)
      default:
        return []
    }
  }

  // 获取趋势线数据范围
  const getTrendRange = processedData => {
    if (!processedData || processedData.length === 0) return '-'

    const allValues = processedData.flatMap(series =>
      (series.data || []).map(item => parseFloat(item.value) || 0)
    )

    if (allValues.length === 0) return '-'

    const min = Math.min(...allValues)
    const max = Math.max(...allValues)

    return `${min.toFixed(2)} ~ ${max.toFixed(2)}`
  }

  // 模板管理函数
  const saveTemplate = () => {
    if (!templateName.value.trim()) {
      alert('请输入模板名称')
      return
    }

    const newTemplate = {
      id: Date.now(),
      name: templateName.value.trim(),
      config: JSON.parse(JSON.stringify(config.value)),
      chartType: config.value.chartType,
      createdAt: new Date().toISOString()
    }

    templates.value.push(newTemplate)
    saveTemplatesToStorage()
    templateName.value = ''
  }

  const loadTemplate = template => {
    selectedTemplate.value = template
  }

  const applyTemplate = template => {
    if (!confirm(`确定要应用模板 "${template.name}" 吗？当前配置将被覆盖。`)) {
      return
    }

    config.value = JSON.parse(JSON.stringify(template.config))
    updateChart()
    alert(`模板 "${template.name}" 已应用`)
  }

  const deleteTemplate = index => {
    if (!confirm('确定要删除这个模板吗？')) {
      return
    }

    // 在删除前保存被删除模板的id，避免数组索引变化导致的错误
    const deletedTemplateId = templates.value[index]?.id
    templates.value.splice(index, 1)
    if (selectedTemplate.value?.id === deletedTemplateId) {
      selectedTemplate.value = null
    }
    saveTemplatesToStorage()
  }

  const exportAllTemplates = () => {
    if (templates.value.length === 0) {
      alert('没有可导出的模板')
      return
    }

    try {
      const blob = new Blob([JSON.stringify(templates.value, null, 2)], {
        type: 'application/json'
      })
      const link = document.createElement('a')
      link.download = `chart-templates-${Date.now()}.json`
      link.href = URL.createObjectURL(blob)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(link.href)
    } catch (error) {
      alert('导出失败，请稍后重试')
    }
  }

  const importTemplates = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.onchange = async event => {
      const file = event.target.files[0]
      if (!file) return

      try {
        const text = await file.text()
        const importedTemplates = JSON.parse(text)

        if (!Array.isArray(importedTemplates)) {
          alert('导入的文件格式不正确')
          return
        }

        const count = importedTemplates.length
        templates.value = [
          ...templates.value,
          ...importedTemplates.map(t => ({ ...t, id: Date.now() + Math.random() }))
        ]
        saveTemplatesToStorage()
        alert(`成功导入 ${count} 个模板`)
      } catch (error) {
        alert('导入失败，请检查文件格式')
      }
    }
    input.click()
  }

  const clearAllTemplates = () => {
    if (!confirm('确定要清空所有模板吗？此操作不可恢复。')) {
      return
    }

    templates.value = []
    selectedTemplate.value = null
    saveTemplatesToStorage()
  }

  const saveTemplatesToStorage = () => {
    try {
      localStorage.setItem('chart-templates', JSON.stringify(templates.value))
    } catch (error) {
      console.error('保存模板失败:', error)
    }
  }

  const loadTemplatesFromStorage = () => {
    try {
      const stored = localStorage.getItem('chart-templates')
      if (stored) {
        templates.value = JSON.parse(stored)
      }
    } catch (error) {
      console.error('加载模板失败:', error)
    }
  }

  // 主题管理函数
  const applyTheme = preset => {
    currentTheme.value = preset.id

    if (preset.id === 'custom') {
      // 自定义主题不自动应用，等待用户手动调整
      return
    }

    const colors = preset.colors
    customTheme.value = { ...colors }

    // 应用主题到当前图表配置
    config.value.backgroundColor = colors.backgroundColor
    config.value.color = colors.primaryColor
    config.value.borderColor = colors.borderColor

    updateChart()
  }

  const applyCustomTheme = () => {
    currentTheme.value = 'custom'
    config.value.backgroundColor = customTheme.value.backgroundColor
    config.value.color = customTheme.value.primaryColor
    config.value.borderColor = customTheme.value.borderColor
    updateChart()
  }

  const getThemePreviewStyle = () => ({
    backgroundColor:
      currentTheme.value === 'custom'
        ? customTheme.value.backgroundColor
        : themePresets.find(t => t.id === currentTheme.value)?.colors?.backgroundColor || '#ffffff',
    color:
      currentTheme.value === 'custom'
        ? customTheme.value.textColor
        : themePresets.find(t => t.id === currentTheme.value)?.colors?.textColor || '#1f2937',
    borderColor:
      currentTheme.value === 'custom'
        ? customTheme.value.borderColor
        : themePresets.find(t => t.id === currentTheme.value)?.colors?.borderColor || '#e5e7eb'
  })

  const themePreviewBarColor = computed(() => {
    if (currentTheme.value === 'custom') {
      return customTheme.value.primaryColor
    }
    return themePresets.find(t => t.id === currentTheme.value)?.colors?.primaryColor || '#3b82f6'
  })

  const exportTheme = () => {
    try {
      const themeData = {
        currentTheme: currentTheme.value,
        customTheme: customTheme.value,
        exportTime: new Date().toISOString()
      }

      const blob = new Blob([JSON.stringify(themeData, null, 2)], { type: 'application/json' })
      const link = document.createElement('a')
      link.download = `chart-theme-${Date.now()}.json`
      link.href = URL.createObjectURL(blob)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(link.href)
    } catch (error) {
      alert('导出主题失败')
    }
  }

  const importTheme = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.onchange = async event => {
      const file = event.target.files[0]
      if (!file) return

      try {
        const text = await file.text()
        const themeData = JSON.parse(text)

        if (themeData.customTheme) {
          customTheme.value = themeData.customTheme
          if (themeData.currentTheme) {
            currentTheme.value = themeData.currentTheme
            applyCustomTheme()
          }
          alert('主题导入成功')
        } else {
          alert('主题文件格式不正确')
        }
      } catch (error) {
        alert('导入主题失败，请检查文件格式')
      }
    }
    input.click()
  }

  const resetTheme = () => {
    if (!confirm('确定要重置为默认主题吗？')) {
      return
    }

    currentTheme.value = 'light'
    customTheme.value = {
      backgroundColor: '#ffffff',
      textColor: '#1f2937',
      primaryColor: '#3b82f6',
      borderColor: '#e5e7eb',
      gridColor: '#e5e7eb'
    }

    applyTheme(themePresets[0])
    alert('主题已重置')
  }

  // 批量操作函数
  const applyBatchColor = () => {
    if (charts.value.length === 0) {
      alert('没有图表可应用')
      return
    }

    const confirmApply = confirm(`确定要将所有图表颜色统一为 ${batchColor.value} 吗？`)
    if (!confirmApply) return

    charts.value.forEach(chart => {
      chart.color = batchColor.value
    })

    // 同步到当前配置
    config.value.color = batchColor.value

    // 更新所有图表
    charts.value.forEach((_, index) => {
      updateChart(index)
    })

    alert(`已将 ${charts.value.length} 个图表颜色统一为 ${batchColor.value}`)
  }

  const applyBatchLegend = () => {
    if (charts.value.length === 0) {
      alert('没有图表可应用')
      return
    }

    charts.value.forEach(chart => {
      chart.showLegend = batchEnableLegend.value
    })

    // 同步到当前配置
    config.value.showLegend = batchEnableLegend.value

    // 更新所有图表
    charts.value.forEach((_, index) => {
      updateChart(index)
    })

    alert(`已将 ${charts.value.length} 个图表的图例设置更新`)
  }

  const applyBatchLabels = () => {
    if (charts.value.length === 0) {
      alert('没有图表可应用')
      return
    }

    charts.value.forEach(chart => {
      chart.showLabel = batchEnableLabels.value
    })

    // 同步到当前配置
    config.value.showLabel = batchEnableLabels.value

    // 更新所有图表
    charts.value.forEach((_, index) => {
      updateChart(index)
    })

    alert(`已将 ${charts.value.length} 个图表的数据标签设置更新`)
  }

  const applyBatchSize = () => {
    if (charts.value.length === 0) {
      alert('没有图表可应用')
      return
    }

    const newWidth = config.value.width
    const newHeight = config.value.height

    charts.value.forEach(chart => {
      chart.width = newWidth
      chart.height = newHeight
    })

    // 调整所有图表实例大小
    charts.value.forEach((_, index) => {
      if (chartInstances.value[index]) {
        chartInstances.value[index].resize()
      }
    })

    alert(`已将 ${charts.value.length} 个图表统一尺寸为 ${newWidth}×${newHeight}`)
  }

  const arrangeInGrid = (cols, rows) => {
    if (charts.value.length === 0) {
      alert('没有图表可排列')
      return
    }

    const padding = 20
    const chartWidth = config.value.width
    const chartHeight = config.value.height
    const gapX = 30
    const gapY = 30

    const startX = 50
    const startY = 50

    charts.value.forEach((chart, index) => {
      const col = index % cols
      const row = Math.floor(index / cols)

      chart.x = startX + col * (chartWidth + gapX)
      chart.y = startY + row * (chartHeight + gapY)
    })

    batchOperation.value = `${cols}x${rows}`
    alert(`已将图表按 ${cols}×${rows} 网格排列`)
  }

  const autoArrange = () => {
    if (charts.value.length === 0) {
      alert('没有图表可排列')
      return
    }

    const containerPadding = 50
    const chartWidth = config.value.width
    const chartHeight = config.value.height
    const displayAreaWidth = 1000 // 假设显示区域宽度
    const gapX = 20
    const gapY = 20

    // 自动计算最佳列数
    const cols = Math.floor(displayAreaWidth / (chartWidth + gapX))
    const rows = Math.ceil(charts.value.length / cols)

    arrangeInGrid(cols, rows)
    batchOperation.value = 'auto'
    alert(`已自动排列图表（${rows}行${cols}列）`)
  }

  const batchExportImages = () => {
    if (charts.value.length === 0) {
      alert('没有图表可导出')
      return
    }

    exportAllImages()
  }

  const batchExportPDF = async () => {
    if (charts.value.length === 0) {
      alert('没有图表可导出')
      return
    }

    alert('PDF导出功能需要引入 jsPDF 库，当前仅支持导出图片和HTML')
    // 实际实现需要：
    // import jsPDF from 'jspdf';
    // const doc = new jsPDF();
    // 遍历图表并添加到PDF
    // doc.save('charts-report.pdf');
  }

  const batchExportZIP = async () => {
    if (charts.value.length === 0) {
      alert('没有图表可导出')
      return
    }

    alert('ZIP压缩导出功能需要引入 JSZip 库，当前仅支持单独导出图片')
    // 实际实现需要：
    // import JSZip from 'jszip';
    // const zip = new JSZip();
    // 遍历图表并添加到ZIP
    // zip.generateAsync({type:"blob"}).then(content => {
    //   const link = document.createElement('a');
    //   link.href = URL.createObjectURL(content);
    //   link.download = 'charts.zip';
    //   link.click();
    // });
  }

  // 智能推荐函数
  const analyzeDataAndRecommend = () => {
    if (!currentDataSource.value) {
      alert('请先导入数据源')
      return
    }

    const data = currentDataSource.value.data
    const fields = currentDataSource.value.fields

    if (!data || data.length === 0) {
      alert('数据源为空，无法分析')
      return
    }

    // 分析数据特征
    const numericFields = []
    const categoricalFields = []
    const dateFields = []

    fields.forEach(field => {
      const sampleValue = data[0][field]
      if (typeof sampleValue === 'number') {
        numericFields.push(field)
      } else if (isDateField(data, field)) {
        dateFields.push(field)
      } else {
        categoricalFields.push(field)
      }
    })

    // 计算数据质量
    const quality = calculateDataQuality(data, fields)

    // 生成分析结果
    analysisResult.value = {
      fieldCount: fields.length,
      rowCount: data.length,
      numericFields,
      categoricalFields,
      dateFields,
      quality
    }

    // 生成推荐
    recommendations.value = generateRecommendations(
      data,
      fields,
      numericFields,
      categoricalFields,
      dateFields,
      quality
    )

    showRecommendations.value = true
  }

  const isDateField = (data, field) => {
    const sample = data.slice(0, 10).map(row => row[field])
    return (
      sample.some(val => !isNaN(Date.parse(val))) ||
      sample.some(val => /^\d{4}-\d{2}-\d{2}/.test(val))
    )
  }

  const calculateDataQuality = (data, fields) => {
    let missingCount = 0
    const totalCells = data.length * fields.length

    data.forEach(row => {
      fields.forEach(field => {
        if (row[field] === null || row[field] === undefined || row[field] === '') {
          missingCount++
        }
      })
    })

    const missingRate = missingCount / totalCells

    if (missingRate < 0.05) return '优秀'
    if (missingRate < 0.15) return '良好'
    if (missingRate < 0.3) return '一般'
    return '较差'
  }

  const generateRecommendations = (
    data,
    fields,
    numericFields,
    categoricalFields,
    dateFields,
    quality
  ) => {
    const recs = []

    // 根据数据特征推荐图表类型
    if (numericFields.length >= 1 && categoricalFields.length >= 1) {
      // 有数值字段和分类字段，推荐柱状图
      recs.push({
        chartType: '柱状图',
        icon: '📊',
        score: 95,
        priority: '高',
        reason: '数据包含数值和分类字段，适合使用柱状图进行对比',
        config: {
          xAxis: categoricalFields[0],
          yAxis: numericFields[0]
        }
      })

      recs.push({
        chartType: '折线图',
        icon: '📈',
        score: 90,
        priority: '高',
        reason: '包含数值和分类字段，折线图适合展示趋势变化',
        config: {
          xAxis: categoricalFields[0],
          yAxis: numericFields[0],
          smooth: true
        }
      })
    }

    if (numericFields.length >= 2) {
      // 多个数值字段，推荐散点图
      recs.push({
        chartType: '散点图',
        icon: '⚡',
        score: 85,
        priority: '中',
        reason: '包含多个数值字段，散点图适合探索数据相关性',
        config: {
          xAxis: numericFields[0],
          yAxis: numericFields[1]
        }
      })
    }

    if (categoricalFields.length >= 2 && numericFields.length >= 1) {
      // 多个分类字段，推荐堆叠柱状图
      recs.push({
        chartType: '堆叠柱状图',
        icon: '📊',
        score: 88,
        priority: '中',
        reason: '有多个分类维度，堆叠图可以查看组成部分',
        config: {
          chartType: 'bar-stack',
          xAxis: categoricalFields[0],
          yAxis: numericFields[0],
          groupField: categoricalFields[1],
          aggregate: 'sum'
        }
      })
    }

    if (dateFields.length >= 1 && numericFields.length >= 1) {
      // 有时间字段，推荐折线图或面积图
      recs.push({
        chartType: '面积图',
        icon: '📊',
        score: 92,
        priority: '高',
        reason: '包含时间序列数据，面积图适合展示累积趋势',
        config: {
          xAxis: dateFields[0],
          yAxis: numericFields[0],
          chartType: 'area'
        }
      })
    }

    if (numericFields.length >= 1 && categoricalFields.length >= 1 && data.length < 10) {
      // 数据量少，适合饼图
      recs.push({
        chartType: '饼图',
        icon: '🥧',
        score: 80,
        priority: '低',
        reason: '数据量较少，饼图可以直观展示占比关系',
        config: {
          chartType: 'pie',
          xAxis: categoricalFields[0],
          yAxis: numericFields[0]
        }
      })

      recs.push({
        chartType: '环形图',
        icon: '🍩',
        score: 78,
        priority: '低',
        reason: '环形图在饼图基础上增加了现代感',
        config: {
          chartType: 'pie-donut',
          xAxis: categoricalFields[0],
          yAxis: numericFields[0]
        }
      })
    }

    // 根据数据质量推荐
    if (
      quality === '优秀' ||
      (quality === '良好' && categoricalFields.length >= 1 && numericFields.length >= 1)
    ) {
      recs.push({
        chartType: '南丁格尔玫瑰图',
        icon: '🌹',
        score: 75,
        priority: '中',
        reason: '数据质量良好，适合使用玫瑰图展示复杂比例关系',
        config: {
          chartType: 'pie-rose',
          xAxis: categoricalFields[0],
          yAxis: numericFields[0]
        }
      })
    }

    // 按评分排序
    recs.sort((a, b) => b.score - a.score)

    return recs.slice(0, 6) // 返回前6个推荐
  }

  const applyRecommendation = rec => {
    if (!confirm(`确定要应用推荐："${rec.chartType}" 吗？当前配置将被覆盖。`)) {
      return
    }

    config.value.chartType = rec.chartType

    if (rec.config) {
      Object.keys(rec.config).forEach(key => {
        if (rec.config[key] !== undefined) {
          config.value[key] = rec.config[key]
        }
      })
    }

    updateChart()
    alert(`已应用推荐：${rec.chartType}`)
  }

  const applyTopRecommendation = () => {
    if (recommendations.value.length === 0) {
      alert('没有可应用的推荐')
      return
    }

    const topRec = recommendations.value[0]
    applyRecommendation(topRec)
  }

  const formatConfigKey = key => {
    const keyMap = {
      xAxis: 'X轴字段',
      yAxis: 'Y轴字段',
      groupField: '分组字段',
      aggregate: '聚合方式',
      chartType: '图表类型',
      smooth: '平滑曲线'
    }
    return keyMap[key] || key
  }

  // 图表管理
  const addNewChart = () => {
    const newChart = {
      id: chartIdCounter++,
      chartType: 'bar',
      xAxis: '',
      yAxis: '',
      xAxisName: '',
      yAxisName: '',
      title: `图表 ${charts.value.length + 1}`,
      showLegend: true,
      showLabel: false,
      dataZoom: false,
      smooth: true,
      lineWidth: 2,
      pieRadius: 60,
      width: 500,
      height: 400,
      x: 50 + charts.value.length * 30,
      y: 50 + charts.value.length * 30,
      color: colorPalette[charts.value.length % colorPalette.length],
      series: [],
      // 动画配置
      animation: {
        enabled: true,
        duration: 1000,
        easing: 'cubicOut'
      },
      // 基础样式增强
      backgroundColor: 'transparent',
      borderRadius: 0,
      borderWidth: 0,
      borderColor: '#e5e7eb',
      symbolSize: 6,
      symbol: 'circle',
      backgroundGradient: null,
      // 标记点
      markPoint: {
        enabled: false,
        data: [],
        symbol: 'pin',
        symbolSize: 50,
        label: {
          show: true
        }
      },
      // 趋势线
      trendLine: {
        enabled: false,
        data: [],
        type: 'average',
        lineStyle: 'solid',
        customValue: 0
      },
      // 多坐标轴配置
      yAxisIndex: 0,
      enableDualAxis: false,
      yAxis2Name: '',
      yAxis2: '',
      seriesAxisIndex: [],
      // 图例配置
      legendConfig: {
        position: 'bottom',
        orient: 'horizontal',
        show: true,
        icon: 'circle',
        selector: false,
        data: []
      },
      // 数据处理配置
      dataProcessing: {
        enabled: false,
        sortBy: '',
        sortOrder: 'asc',
        filterCondition: '',
        filterValue: '',
        topN: 0
      }
    }

    charts.value.push(newChart)
    selectedChartIndex.value = charts.value.length - 1
    config.value = { ...newChart }

    setTimeout(() => {
      initChart(charts.value.length - 1)
    }, 100)
  }

  const duplicateChart = index => {
    const originalChart = charts.value[index]
    const newChart = {
      ...originalChart,
      id: chartIdCounter++,
      title: `${originalChart.title} (副本)`,
      x: originalChart.x + 30,
      y: originalChart.y + 30,
      series: JSON.parse(JSON.stringify(originalChart.series))
    }

    charts.value.push(newChart)
    selectedChartIndex.value = charts.value.length - 1
    config.value = { ...newChart }

    nextTick(() => {
      initChart(charts.value.length - 1)
    })
  }

  const deleteChart = index => {
    if (charts.value.length === 0) return

    if (chartInstances.value[index]) {
      chartInstances.value[index].dispose()
      delete chartInstances.value[index]
    }

    charts.value.splice(index, 1)

    if (selectedChartIndex.value >= charts.value.length) {
      selectedChartIndex.value = charts.value.length - 1
    }

    if (charts.value.length > 0) {
      const newIndex = selectedChartIndex.value
      if (newIndex >= 0) {
        selectChart(newIndex)
      }
    }
  }

  const selectChart = index => {
    selectedChartIndex.value = index
    if (charts.value[index]) {
      config.value = { ...charts.value[index] }
    }
  }

  const setChartRef = (el, index) => {
    if (el) {
      chartDoms.value[index] = el
    }
  }

  const getChartStyle = chartItem => ({
    width: `${chartItem.width}px`,
    height: `${chartItem.height}px`,
    left: `${chartItem.x}px`,
    top: `${chartItem.y}px`,
    position: 'absolute'
  })

  // 图表初始化和更新
  const initChart = index => {
    if (chartDoms.value[index] && !chartInstances.value[index]) {
      chartInstances.value[index] = echarts.init(chartDoms.value[index])
      updateChart(index)
    }
  }

  const updateChart = index => {
    const chartIndex = index !== undefined ? index : selectedChartIndex.value
    const instance = chartInstances.value[chartIndex]
    const chartConfig = charts.value[chartIndex]

    if (!chartConfig) return

    const useMultiSeries = chartConfig?.series && chartConfig.series.length > 0
    charts.value[chartIndex] = { ...chartConfig }

    if (!instance) return

    if (!chartConfig?.xAxis) {
      instance.clear()
      return
    }

    if (!useMultiSeries && !chartConfig?.yAxis) {
      instance.clear()
      return
    }

    let processedData = null
    if (!useMultiSeries && currentDataSource.value) {
      processedData = processData(currentDataSource.value.data, chartConfig)
    }

    const option = generateChartOption(processedData, chartConfig)
    instance.setOption(option, true)
  }

  const refreshConfig = () => {
    if (selectedChartIndex.value !== null && charts.value[selectedChartIndex.value]) {
      config.value = { ...charts.value[selectedChartIndex.value] }
    }
  }

  const clearAll = () => {
    Object.keys(chartInstances.value).forEach(key => {
      chartInstances.value[key].dispose()
    })
    chartInstances.value = {}

    charts.value = []
    selectedChartIndex.value = 0
    chartIdCounter = 0
  }

  const processData = (rawData, chartConfig) => {
    const { xAxis, yAxis, groupField, aggregate, dataProcessing } = chartConfig || config.value

    // 应用数据处理
    let data = [...rawData]

    if (dataProcessing?.enabled) {
      const { sortBy, sortOrder, filterCondition, filterValue, topN } = dataProcessing

      // 过滤
      if (filterCondition && filterValue) {
        const filterValues = filterValue.split(',').map(v => v.trim().toLowerCase())
        data = data.filter(row => {
          const rowValue = String(row[filterCondition] || '').toLowerCase()
          return filterValues.some(fv => rowValue.includes(fv))
        })
      }

      // 排序
      if (sortBy) {
        data.sort((a, b) => {
          const aVal = a[sortBy]
          const bVal = b[sortBy]

          if (typeof aVal === 'number' && typeof bVal === 'number') {
            return sortOrder === 'asc' ? aVal - bVal : bVal - aVal
          }

          const aStr = String(aVal || '').toLowerCase()
          const bStr = String(bVal || '').toLowerCase()

          return sortOrder === 'asc' ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr)
        })
      }

      // Top N
      if (topN > 0) {
        data = data.slice(0, topN)
      }
    }

    const processed = []

    if (groupField && aggregate !== 'none') {
      const groups = {}

      data.forEach(row => {
        const groupKey = row[groupField]
        const xValue = row[xAxis]
        const yValue = parseFloat(row[yAxis]) || 0

        if (!groups[groupKey]) {
          groups[groupKey] = []
        }

        groups[groupKey].push({ x: xValue, y: yValue })
      })

      Object.keys(groups).forEach(groupKey => {
        const groupData = groups[groupKey]
        const aggregated = {}

        groupData.forEach(item => {
          if (!aggregated[item.x]) {
            aggregated[item.x] = []
          }
          aggregated[item.x].push(item.y)
        })

        const seriesData = []
        Object.keys(aggregated).forEach(xValue => {
          const values = aggregated[xValue]
          let result

          switch (aggregate) {
            case 'sum':
              result = values.reduce((a, b) => a + b, 0)
              break
            case 'avg':
              result = values.reduce((a, b) => a + b, 0) / values.length
              break
            case 'count':
              result = values.length
              break
            case 'max':
              result = Math.max(...values)
              break
            case 'min':
              result = Math.min(...values)
              break
            default:
              result = values[0]
          }

          seriesData.push({ name: xValue, value: result })
        })

        processed.push({
          name: groupKey,
          data: seriesData.sort((a, b) => a.name.localeCompare(b.name))
        })
      })
    } else if (aggregate !== 'none') {
      const aggregated = {}

      data.forEach(row => {
        const xValue = row[xAxis]
        const yValue = parseFloat(row[yAxis]) || 0

        if (!aggregated[xValue]) {
          aggregated[xValue] = []
        }
        aggregated[xValue].push(yValue)
      })

      const seriesData = []
      Object.keys(aggregated).forEach(xValue => {
        const values = aggregated[xValue]
        let result

        switch (aggregate) {
          case 'sum':
            result = values.reduce((a, b) => a + b, 0)
            break
          case 'avg':
            result = values.reduce((a, b) => a + b, 0) / values.length
            break
          case 'count':
            result = values.length
            break
          case 'max':
            result = Math.max(...values)
            break
          case 'min':
            result = Math.min(...values)
            break
          default:
            result = values[0]
        }

        seriesData.push({ name: xValue, value: result })
      })

      processed.push({
        name: '数据系列',
        data: seriesData.sort((a, b) => a.name.localeCompare(b.name))
      })
    } else {
      const seriesData = data.map(row => ({
        name: row[xAxis],
        value: parseFloat(row[yAxis]) || 0
      }))

      processed.push({
        name: '数据系列',
        data: seriesData
      })
    }

    return processed
  }

  const processMultiSeriesData = chartConfig => {
    const { xAxis, series } = chartConfig || config.value

    if (!series || series.length === 0) return []

    const allProcessedData = []

    series.forEach(seriesConfig => {
      const dataSource = dataSources.value[seriesConfig.dataSourceIndex]
      if (!dataSource || !seriesConfig.yAxis) return

      const seriesProcessed = processData(dataSource.data, {
        xAxis,
        yAxis: seriesConfig.yAxis,
        groupField: seriesConfig.groupField,
        aggregate: seriesConfig.aggregate
      })

      seriesProcessed.forEach(group => {
        allProcessedData.push({
          ...group,
          seriesName: seriesConfig.seriesName || group.name,
          seriesType: seriesConfig.seriesType,
          color: seriesConfig.color
        })
      })
    })

    return allProcessedData
  }

  const generateChartOption = (processedData, chartConfig) => {
    const {
      title,
      xAxisName,
      yAxisName,
      showLegend,
      showLabel,
      series,
      chartType,
      color,
      dataZoom,
      smooth,
      lineWidth,
      pieRadius,
      animation,
      backgroundColor,
      borderRadius,
      borderWidth,
      borderColor,
      symbol,
      symbolSize,
      markPoint,
      trendLine
    } = chartConfig || config.value

    const useMultiSeries = series && series.length > 0

    const baseOption = {
      title: {
        text: title || '数据可视化图表',
        left: 'center',
        top: 20,
        textStyle: {
          fontSize: 18,
          fontWeight: 600
        }
      },
      tooltip: {
        trigger: useMultiSeries ? 'axis' : 'item',
        axisPointer: {
          type: 'cross'
        },
        backgroundColor: 'rgba(255, 255, 255, 0.95)',
        borderColor: '#e5e7eb',
        borderWidth: 1,
        padding: [12, 16],
        textStyle: {
          color: '#1f2937'
        }
      },
      legend: {
        show: showLegend,
        orient: chartConfig.legendConfig?.orient || 'horizontal',
        top: chartConfig.legendConfig?.position === 'top' ? 10 : undefined,
        bottom: chartConfig.legendConfig?.position === 'bottom' ? 10 : undefined,
        left: chartConfig.legendConfig?.position === 'left' ? 10 : undefined,
        right: chartConfig.legendConfig?.position === 'right' ? 10 : undefined,
        textStyle: {
          color: '#374151'
        },
        icon: chartConfig.legendConfig?.icon !== 'none' ? chartConfig.legendConfig?.icon : undefined
      },
      grid: {
        left: '10%',
        right: '10%',
        bottom: showLegend ? '15%' : '10%',
        top: '15%',
        containLabel: true
      },
      animation:
        animation && animation.enabled
          ? {
              duration: animation.duration,
              easing: animation.easing
            }
          : false
    }

    // 应用背景样式
    if (backgroundColor && backgroundColor !== 'transparent') {
      baseOption.backgroundColor = backgroundColor
    }

    // 应用数据点样式辅助函数
    const applyPointStyles = seriesItem => {
      const baseStyles = {
        symbol: symbol,
        symbolSize: symbolSize
      }

      if (borderRadius && borderRadius > 0) {
        seriesItem.itemStyle = seriesItem.itemStyle || {}
        seriesItem.itemStyle.borderRadius = borderRadius
      }

      if (borderWidth > 0) {
        seriesItem.itemStyle = seriesItem.itemStyle || {}
        seriesItem.itemStyle.borderColor = borderColor
        seriesItem.itemStyle.borderWidth = borderWidth
      }

      return { ...seriesItem, ...baseStyles }
    }

    // 饼图类型（包括变体）
    if (['pie', 'pie-donut', 'pie-rose', 'pie-double'].includes(chartType)) {
      if (!processedData || processedData.length === 0) {
        return baseOption
      }
      const allData = processedData.flatMap(series => series.data || [])

      const pieConfig = {
        type: 'pie',
        data: allData,
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        },
        label: {
          show: true,
          formatter: '{b}: {d}%'
        }
      }

      // 根据类型配置不同的饼图样式
      switch (chartType) {
        case 'pie':
          pieConfig.radius = [`${pieRadius - 20}%`, `${pieRadius}%`]
          pieConfig.itemStyle = {
            borderRadius: 8,
            borderColor: '#fff',
            borderWidth: 2
          }
          break
        case 'pie-donut':
          pieConfig.radius = [`${pieRadius - 30}%`, `${pieRadius}%`]
          pieConfig.itemStyle = {
            borderRadius: 10,
            borderColor: '#fff',
            borderWidth: 3
          }
          pieConfig.label = {
            show: true,
            formatter: '{b}\n{d}%'
          }
          break
        case 'pie-rose':
          pieConfig.radius = [0, `${pieRadius}%`]
          pieConfig.roseType = 'radius'
          pieConfig.itemStyle = {
            borderRadius: 8,
            borderColor: '#fff',
            borderWidth: 2
          }
          break
        case 'pie-double':
          const midIndex = Math.floor(allData.length / 2)
          pieConfig.seriesName = '内环'
          pieConfig.radius = [`${pieRadius - 50}%`, `${pieRadius - 20}%`]
          pieConfig.data = allData.slice(0, midIndex)
          pieConfig.itemStyle = {
            borderRadius: 8,
            borderColor: '#fff',
            borderWidth: 2
          }

          baseOption.series = [
            pieConfig,
            {
              ...pieConfig,
              seriesName: '外环',
              radius: [`${pieRadius - 10}%`, `${pieRadius}%`],
              data: allData.slice(midIndex)
            }
          ]
          baseOption.legend = {
            ...baseOption.legend,
            data: [
              ...allData.slice(0, midIndex).map(d => d.name),
              ...allData.slice(midIndex).map(d => d.name)
            ]
          }
          return baseOption
      }

      baseOption.series = [pieConfig]
    } else if (chartType === 'radar') {
      if (!processedData || processedData.length === 0) {
        return baseOption
      }

      const indicator = processedData[0].data.map(item => ({
        name: item.name,
        max: Math.max(...processedData[0].data.map(d => d.value)) * 1.2
      }))

      baseOption.radar = {
        indicator: indicator,
        shape: 'circle',
        splitNumber: 5,
        name: {
          textStyle: {
            color: '#374151'
          }
        },
        splitLine: {
          lineStyle: {
            color: '#e5e7eb'
          }
        },
        splitArea: {
          show: false
        },
        axisLine: {
          lineStyle: {
            color: '#e5e7eb'
          }
        }
      }

      baseOption.series = processedData.map(s => ({
        name: s.name,
        type: 'radar',
        data: [
          {
            value: s.data.map(d => d.value),
            name: s.name
          }
        ],
        lineStyle: {
          width: lineWidth,
          color: color
        },
        areaStyle: {
          color: color,
          opacity: 0.3
        },
        symbolSize: 6
      }))
    } else if (chartType === 'funnel') {
      if (!processedData || processedData.length === 0) {
        return baseOption
      }

      baseOption.series = processedData.map(s => ({
        name: s.name,
        type: 'funnel',
        left: '10%',
        width: '80%',
        maxSize: '80%',
        label: {
          show: true,
          fontSize: 14
        },
        labelLine: {
          length: 10,
          lineStyle: {
            width: 1,
            type: 'solid'
          }
        },
        itemStyle: {
          borderWidth: 0
        },
        emphasis: {
          label: {
            fontSize: 16
          }
        },
        data: s.data
          .sort((a, b) => b.value - a.value)
          .map((d, i) => ({ ...d, itemStyle: { color: colorPalette[i % colorPalette.length] } }))
      }))
    } else if (chartType === 'gauge') {
      if (!processedData || processedData.length === 0) {
        return baseOption
      }

      const total = processedData[0].data.reduce((sum, d) => sum + d.value, 0)
      const value = processedData[0].data[0]?.value || 0

      baseOption.series = [
        {
          type: 'gauge',
          startAngle: 180,
          endAngle: 0,
          min: 0,
          max: total * 1.2,
          splitNumber: 8,
          axisLine: {
            lineStyle: {
              width: 6,
              color: [
                [0.25, '#FF6E76'],
                [0.5, '#FDDD60'],
                [0.75, '#58D9F9'],
                [1, '#7CFFB2']
              ]
            }
          },
          pointer: {
            icon: 'path://M12.8,0.7l12,40.1H25.1L12.8,0.7z',
            length: '12%',
            width: 20,
            offsetCenter: [0, '-60%'],
            itemStyle: {
              color: 'auto'
            }
          },
          axisTick: {
            length: 12,
            lineStyle: {
              color: 'auto',
              width: 2
            }
          },
          splitLine: {
            length: 20,
            lineStyle: {
              color: 'auto',
              width: 5
            }
          },
          axisLabel: {
            color: '#464646',
            fontSize: 14,
            distance: -60
          },
          title: {
            offsetCenter: [0, '-70%'],
            fontSize: 20
          },
          detail: {
            fontSize: 40,
            offsetCenter: [0, '0%'],
            valueAnimation: true,
            formatter: function (value) {
              return '{value|' + value.toFixed(0) + '}'
            },
            rich: {
              value: {
                fontSize: 40,
                fontWeight: 'bold',
                color: '#1f2937'
              }
            }
          },
          data: [
            {
              value: value,
              name: processedData[0].data[0]?.name || '数值'
            }
          ]
        }
      ]
    } else {
      if (!processedData || processedData.length === 0) {
        return baseOption
      }

      const xAxisData = processedData[0]?.data?.map(item => item.name) || []

      baseOption.xAxis = {
        type: 'category',
        name: xAxisName,
        data: xAxisData,
        axisLabel: {
          color: '#374151'
        },
        axisLine: {
          lineStyle: {
            color: '#e5e7eb'
          }
        }
      }

      baseOption.yAxis = {
        type: 'value',
        name: yAxisName,
        axisLabel: {
          color: '#374151'
        },
        axisLine: {
          show: false
        },
        splitLine: {
          lineStyle: {
            color: '#e5e7eb',
            type: 'dashed'
          }
        }
      }

      if (dataZoom) {
        baseOption.dataZoom = [
          {
            type: 'slider',
            show: true,
            xAxisIndex: [0],
            start: 0,
            end: 100,
            height: 20,
            bottom: 40
          },
          {
            type: 'inside',
            xAxisIndex: [0],
            start: 0,
            end: 100
          }
        ]
      }

      baseOption.color = [color]

      // 根据图表类型配置系列
      const chartTypeMapping = {
        bar: 'bar',
        'bar-stack': 'bar',
        'bar-group': 'bar',
        'bar-percent': 'bar',
        line: 'line',
        'line-step': 'line',
        area: 'line',
        'area-step': 'line',
        scatter: 'scatter'
      }

      const effectiveChartType = chartTypeMapping[chartType] || chartType

      baseOption.series = processedData.map((s, index) => {
        const seriesConfig = applyPointStyles({
          name: s.name,
          type: effectiveChartType,
          data: s.data.map(item => item.value),
          label: {
            show: showLabel,
            position: 'top',
            color: '#374151'
          }
        })

        // 堆叠配置
        if (chartType === 'bar-stack' || chartType === 'bar-percent') {
          seriesConfig.stack = 'total'

          if (chartType === 'bar-percent') {
            seriesConfig.yAxis = {
              type: 'value',
              max: 100,
              axisLabel: {
                formatter: '{value}%'
              }
            }
            // 将数据转换为百分比
            const total = processedData.reduce((sum, series) => {
              const seriesData = series.data.map(item => item.value)
              return sum + seriesData[s.data.length - 1] || 0
            }, 0)
            seriesConfig.data = s.data.map((item, i) => {
              const columnIndex = i
              const columnTotal = processedData.reduce((colSum, series) => {
                return colSum + (series.data[columnIndex]?.value || 0)
              }, 0)
              return columnTotal > 0 ? ((item.value / columnTotal) * 100).toFixed(2) : 0
            })
          }
        }

        // 阶梯图配置
        if (chartType === 'line-step' || chartType === 'area-step') {
          seriesConfig.step = 'start'
          seriesConfig.smooth = false
        } else if (effectiveChartType === 'line') {
          seriesConfig.smooth = smooth
          seriesConfig.lineStyle = {
            width: lineWidth
          }
        }

        // 面积图配置
        if (chartType === 'area' || chartType === 'area-step') {
          seriesConfig.areaStyle = {
            color: color,
            opacity: 0.3
          }
        }

        // 散点图配置
        if (effectiveChartType === 'scatter') {
          seriesConfig.symbolSize = 10
        }

        // 分组柱状图需要为每个系列创建独立的柱状
        if (chartType === 'bar-group' && processedData.length > 1) {
          const barWidth = 80 / processedData.length
          seriesConfig.barWidth = `${barWidth}%`
          seriesConfig.barGap = '0%'
        }

        return seriesConfig
      })

      // 分组柱状图特殊的xAxis配置
      if (chartType === 'bar-group') {
        baseOption.xAxis.axisTick = {
          alignWithLabel: true
        }
      }
    }

    if (useMultiSeries) {
      const firstDataSource = dataSources.value[series[0].dataSourceIndex]
      baseOption.xAxis = {
        type: 'category',
        name: xAxisName,
        data: firstDataSource?.data?.map(row => row[chartConfig.xAxis]) || [],
        axisLabel: {
          color: '#374151'
        }
      }

      // 配置Y轴（支持双Y轴）
      if (chartConfig.enableDualAxis) {
        baseOption.yAxis = [
          {
            type: 'value',
            name: yAxisName,
            position: 'left',
            axisLabel: {
              color: '#374151'
            },
            axisLine: {
              lineStyle: {
                color: '#3b82f6'
              }
            },
            splitLine: {
              lineStyle: {
                color: '#e5e7eb',
                type: 'dashed'
              }
            }
          },
          {
            type: 'value',
            name: yAxis2Name || '右侧Y轴',
            position: 'right',
            axisLabel: {
              color: '#374151'
            },
            axisLine: {
              lineStyle: {
                color: '#ef4444'
              }
            },
            splitLine: {
              show: false
            }
          }
        ]
      } else {
        baseOption.yAxis = {
          type: 'value',
          name: yAxisName,
          axisLabel: {
            color: '#374151'
          }
        }
      }

      if (dataZoom) {
        baseOption.dataZoom = [
          {
            type: 'slider',
            show: true,
            xAxisIndex: [0],
            start: 0,
            end: 100
          },
          {
            type: 'inside',
            xAxisIndex: [0],
            start: 0,
            end: 100
          }
        ]
      }

      const allSeriesConfig = []

      series.forEach((seriesConfig, index) => {
        const dataSource = dataSources.value[seriesConfig.dataSourceIndex]
        if (!dataSource || !seriesConfig.yAxis) return

        const seriesProcessed = processData(dataSource.data, {
          xAxis: chartConfig.xAxis,
          yAxis: seriesConfig.yAxis,
          groupField: seriesConfig.groupField,
          aggregate: seriesConfig.aggregate
        })

        seriesProcessed.forEach(group => {
          allSeriesConfig.push({
            name: seriesConfig.seriesName || group.name,
            type: seriesConfig.seriesType,
            data: group.data.map(item => item.value),
            color: seriesConfig.color,
            smooth: smooth,
            linewidth: lineWidth,
            yAxisIndex: seriesConfig.yAxisIndex !== undefined ? seriesConfig.yAxisIndex : 0,
            label: {
              show: showLabel,
              position: 'top'
            }
          })
        })
      })

      baseOption.series = allSeriesConfig

      // 应用标记点到多系列图表
      if (markPoint && markPoint.enabled && markPoint.data && markPoint.data.length > 0) {
        baseOption.series.forEach((series, index) => {
          series.markPoint = {
            data: markPoint.data.map(point => ({
              ...point,
              itemStyle: {
                color: series.color || colorPalette[index % colorPalette.length]
              }
            })),
            symbol: markPoint.symbol === 'none' ? undefined : markPoint.symbol,
            symbolSize: markPoint.symbolSize,
            label: {
              show: true,
              formatter: '{b}: {c}'
            }
          }
        })
      }

      // 应用趋势线到多系列图表
      if (
        trendLine &&
        trendLine.enabled &&
        (chartType === 'bar' ||
          chartType === 'bar-stack' ||
          chartType === 'bar-group' ||
          chartType === 'bar-percent' ||
          chartType === 'line' ||
          chartType === 'line-step' ||
          chartType === 'area' ||
          chartType === 'area-step')
      ) {
        if (processedData && processedData.length > 0) {
          const trendValues = calculateTrendLine(processedData[0].data, trendLine.type)
          if (trendValues.length > 0) {
            baseOption.series.forEach(series => {
              series.markLine = {
                symbol: trendLine.type === 'custom' ? 'none' : 'arrow',
                symbolSize: [8, 8],
                label: {
                  show: true,
                  formatter: params => {
                    const typeMap = {
                      average: '平均值',
                      max: '最大值',
                      min: '最小值',
                      median: '中位数',
                      custom: '自定义'
                    }
                    return typeMap[trendLine.type] || ''
                  }
                },
                lineStyle: {
                  type: trendLine.lineStyle || 'solid',
                  color: '#ef4444',
                  width: 2
                },
                data: [
                  {
                    type: 'average',
                    name: trendLine.type
                  }
                ]
              }
            })
          }
        }
      }
    }

    // 应用标记点到单系列图表
    if (
      !useMultiSeries &&
      markPoint &&
      markPoint.enabled &&
      markPoint.data &&
      markPoint.data.length > 0
    ) {
      if (baseOption.series && baseOption.series[0]) {
        baseOption.series[0].markPoint = {
          data: markPoint.data.map(point => ({
            ...point,
            itemStyle: {
              color: color
            }
          })),
          symbol: markPoint.symbol === 'none' ? undefined : markPoint.symbol,
          symbolSize: markPoint.symbolSize,
          label: {
            show: true,
            formatter: '{b}: {c}'
          }
        }
      }
    }

    // 应用趋势线到单系列图表
    if (
      !useMultiSeries &&
      trendLine &&
      trendLine.enabled &&
      processedData &&
      processedData.length > 0
    ) {
      if (baseOption.series && baseOption.series[0]) {
        const trendValues = calculateTrendLine(processedData[0].data, trendLine.type)
        if (trendValues.length > 0) {
          baseOption.series[0].markLine = {
            symbol: trendLine.type === 'custom' ? 'none' : 'arrow',
            symbolSize: [8, 8],
            label: {
              show: true,
              formatter: params => {
                const typeMap = {
                  average: '平均值',
                  max: '最大值',
                  min: '最小值',
                  median: '中位数',
                  custom: '自定义'
                }
                return typeMap[trendLine.type] || ''
              }
            },
            lineStyle: {
              type: trendLine.lineStyle || 'solid',
              color: '#ef4444',
              width: 2
            },
            data: [
              {
                type: 'average',
                name: trendLine.type
              }
            ]
          }
        }
      }
    }

    return baseOption
  }

  const handleResize = () => {
    Object.keys(chartInstances.value).forEach(key => {
      if (chartInstances.value[key]) {
        chartInstances.value[key].resize()
      }
    })
  }

  // 拖拽和调整大小
  const activeDragIndex = ref(null)
  const activeResizeIndex = ref(null)

  const startDrag = (e, index) => {
    const chart = charts.value[index]
    if (!chart) return

    e.preventDefault()
    e.stopPropagation()
    activeDragIndex.value = index

    const startX = e.clientX - chart.x
    const startY = e.clientY - chart.y

    const onMouseMove = moveEvent => {
      if (activeDragIndex.value !== index) return
      chart.x = moveEvent.clientX - startX
      chart.y = moveEvent.clientY - startY
    }

    const onMouseUp = () => {
      activeDragIndex.value = null
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  const startResize = (e, index) => {
    const chart = charts.value[index]
    if (!chart) return

    e.preventDefault()
    e.stopPropagation()
    activeResizeIndex.value = index

    const startX = e.clientX
    const startY = e.clientY
    const startWidth = chart.width
    const startHeight = chart.height

    const onMouseMove = moveEvent => {
      if (activeResizeIndex.value !== index) return
      chart.width = Math.max(300, startWidth + (moveEvent.clientX - startX))
      chart.height = Math.max(200, startHeight + (moveEvent.clientY - startY))

      if (chartInstances.value[index]) {
        chartInstances.value[index].resize()
      }
    }

    const onMouseUp = () => {
      activeResizeIndex.value = null
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  // 导出功能
  const exportSingleImage = () => {
    if (charts.value.length === 0) {
      alert('没有可导出的图表')
      return
    }

    const instance = chartInstances.value[selectedChartIndex.value]
    if (!instance) {
      alert('图表实例不存在')
      return
    }

    try {
      const url = instance.getDataURL({
        type: 'png',
        pixelRatio: 2,
        backgroundColor: isDarkTheme.value ? '#1f2937' : '#fff'
      })

      const link = document.createElement('a')
      link.download = `chart-${charts.value[selectedChartIndex.value]?.title || 'export'}-${Date.now()}.png`
      link.href = url
      link.click()

      showExportMenu.value = false
    } catch (error) {
      alert('导出失败，请稍后重试')
    }
  }

  const exportAllImages = () => {
    if (charts.value.length === 0) {
      alert('没有可导出的图表')
      return
    }

    let exportCount = 0
    const totalCount = charts.value.length

    charts.value.forEach((chart, index) => {
      const instance = chartInstances.value[index]
      if (instance) {
        try {
          const url = instance.getDataURL({
            type: 'png',
            pixelRatio: 2,
            backgroundColor: isDarkTheme.value ? '#1f2937' : '#fff'
          })

          const link = document.createElement('a')
          link.download = `${chart.title || 'chart'}-${index + 1}-${Date.now()}.png`
          link.href = url
          link.click()
          exportCount++
        } catch (error) {
          // 静默处理
        }
      }
    })

    showExportMenu.value = false
  }

  const exportHTML = () => {
    if (charts.value.length === 0) {
      alert('没有可导出的图表')
      return
    }

    try {
      const maxWidth = Math.max(...charts.value.map(c => c.x + c.width))
      const maxHeight = Math.max(...charts.value.map(c => c.y + c.height))
      const padding = 20
      const totalWidth = maxWidth + padding * 2
      const totalHeight = maxHeight + padding * 2

      const chartsData = charts.value.map((chart, index) => ({
        id: index,
        title: chart.title,
        x: chart.x,
        y: chart.y,
        width: chart.width,
        height: chart.height,
        option: chartInstances.value[index] ? chartInstances.value[index].getOption() : null
      }))

      const htmlTemplate = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据可视化报告 - ${new Date().toLocaleDateString('zh-CN')}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@6.0.0/dist/echarts.min.js"><\/script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }
        .header h1 { color: #111827; font-size: 28px; margin-bottom: 10px; }
        .header .meta { color: #6b7280; font-size: 14px; }
        .canvas-container {
            background: white;
            border-radius: 12px;
            padding: ${padding}px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            position: relative;
            width: ${totalWidth}px;
            min-height: ${totalHeight}px;
        }
        .chart-item {
            position: absolute;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            background: #fff;
        }
        .chart-dom { width: 100%; height: 100%; }
        .footer {
            margin-top: 20px;
            text-align: center;
            color: #6b7280;
            font-size: 12px;
            padding: 10px;
            background: white;
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>数据可视化报告</h1>
        <div class="meta">
            <p>导出时间: ${new Date().toLocaleString('zh-CN')}</p>
            <p>图表数量: ${charts.value.length}</p>
        </div>
    </div>
    <div class="canvas-container">
        ${chartsData
          .map(
            (chart, index) => `
        <div class="chart-item" style="left: ${chart.x}px; top: ${chart.y}px; width: ${chart.width}px; height: ${chart.height}px;">
            <div id="chart-${chart.id}" class="chart-dom"></div>
        </div>
        `
          )
          .join('')}
    </div>
    <div class="footer">
        <p>由 AI Code Frontend 生成 | 包含 ${charts.value.length} 个图表</p>
    </div>
    <script>
        const chartsData = ${JSON.stringify(
          chartsData.filter(c => c.option),
          null,
          2
        )};
        chartsData.forEach(chart => {
            try {
                const dom = document.getElementById('chart-' + chart.id);
                if (dom) {
                    const instance = echarts.init(dom);
                    instance.setOption(chart.option);
                }
            } catch (error) {
                console.error('初始化图表失败:', chart.id, error);
            }
        });
        window.addEventListener('resize', function() {
            chartsData.forEach(chart => {
                const dom = document.getElementById('chart-' + chart.id);
                if (dom) {
                    const instance = echarts.getInstanceByDom(dom);
                    if (instance) instance.resize();
                }
            });
        });
    <\/script>
</body>
</html>`

      const blob = new Blob([htmlTemplate], { type: 'text/html;charset=utf-8' })
      const link = document.createElement('a')
      link.download = `charts-report-${Date.now()}.html`
      link.href = URL.createObjectURL(blob)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(link.href)

      showExportMenu.value = false
    } catch (error) {
      alert('导出失败，请稍后重试')
    }
  }

  const exportConfig = () => {
    if (charts.value.length === 0) {
      alert('没有可导出的配置')
      return
    }

    try {
      const config = {
        charts: charts.value.map(chart => ({
          title: chart.title,
          chartType: chart.chartType,
          xAxis: chart.xAxis,
          yAxis: chart.yAxis,
          xAxisName: chart.xAxisName,
          yAxisName: chart.yAxisName,
          showLegend: chart.showLegend,
          showLabel: chart.showLabel,
          dataZoom: chart.datazoom,
          smooth: chart.smooth,
          lineWidth: chart.lineWidth,
          pieRadius: chart.pieRadius,
          color: chart.color,
          series: chart.series
        })),
        exportTime: new Date().toISOString()
      }

      const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' })
      const link = document.createElement('a')
      link.download = `chart-config-${Date.now()}.json`
      link.href = URL.createObjectURL(blob)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(link.href)

      showExportMenu.value = false
    } catch (error) {
      alert('导出配置失败')
    }
  }

  const closeEditor = () => {
    showExportMenu.value = false
    activeDragIndex.value = null
    activeResizeIndex.value = null
    emit('close')
  }

  // 生命周期
  onMounted(() => {
    window.addEventListener('resize', handleResize)
    loadTemplatesFromStorage()
  })

  onBeforeUnmount(() => {
    Object.keys(chartInstances.value).forEach(key => {
      chartInstances.value[key].dispose()
    })
    chartInstances.value = {}

    if (typeof handleResize === 'function') {
      window.removeEventListener('resize', handleResize)
    }
  })

  // 监听 visible 变化
  watch(
    () => props.visible,
    (newVal, oldVal) => {
      if (newVal && !oldVal) {
        if (charts.value.length === 0) {
          setTimeout(() => {
            addNewChart()
          }, 200)
        } else {
          setTimeout(() => {
            charts.value.forEach((_, index) => {
              initChart(index)
            })
          }, 200)
        }
      } else if (!newVal) {
        activeDragIndex.value = null
        activeResizeIndex.value = null
      }
    }
  )

  // 监听数据源变化
  watch(
    [dataSources, selectedDataSourceIndex],
    () => {
      if (currentDataSource.value && charts.value.length > 0) {
        charts.value.forEach((_, index) => {
          updateChart(index)
        })
      }
    },
    { deep: true }
  )

  // 监听当前图表配置变化
  watch(
    config,
    newConfig => {
      if (selectedChartIndex.value !== null && charts.value[selectedChartIndex.value]) {
        charts.value[selectedChartIndex.value] = { ...newConfig }
        updateChart(selectedChartIndex.value)
      }
    },
    { deep: true }
  )
</script>

<style scoped>
  .chart-editor-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 9999;
    overflow: hidden;
  }

  .chart-editor-container {
    width: 95vw;
    height: 95vh;
    max-width: 1800px;
    max-height: 1000px;
    background: var(--bg-primary);
    border-radius: 16px;
    display: flex;
    flex-direction: column;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    overflow: hidden;
  }

  /* 头部样式 */
  .editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 28px;
    border-bottom: 1px solid #e5e7eb;
    background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .editor-header h2 {
    margin: 0;
    font-size: 24px;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .header-stats {
    display: flex;
    gap: 12px;
    font-size: 13px;
    color: #6b7280;
  }

  .stat-item {
    padding: 4px 12px;
    background: white;
    border-radius: 20px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .header-btn {
    width: 36px;
    height: 36px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: white;
    font-size: 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .header-btn:hover {
    background: #f9fafb;
    border-color: #3b82f6;
    transform: translateY(-1px);
  }

  .close-btn {
    width: 36px;
    height: 36px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: white;
    font-size: 20px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: #fee2e2;
    border-color: #ef4444;
    color: #ef4444;
  }

  /* 主内容区 */
  .editor-content {
    display: flex;
    flex: 1;
    overflow: hidden;
  }

  .editor-content.dark-theme {
    background: #1f2937;
  }

  /* 配置面板 */
  .config-panel {
    width: 400px;
    padding: 20px;
    overflow-y: auto;
    border-right: 1px solid #e5e7eb;
    background: linear-gradient(180deg, #f9fafb 0%, #fff 100%);
  }

  .panel-section {
    margin-bottom: 24px;
    background: white;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }

  .section-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 700;
    color: #1f2937;
    margin-bottom: 16px;
  }

  .title-icon {
    font-size: 20px;
  }

  .collapse-btn {
    margin-left: auto;
    background: none;
    border: none;
    color: #9ca3af;
    cursor: pointer;
    font-size: 12px;
    padding: 4px 8px;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .collapse-btn:hover {
    background: #f3f4f6;
    color: #6b7280;
  }

  /* 上传区域 */
  .upload-area {
    border: 2px dashed #d1d5db;
    border-radius: 12px;
    padding: 32px 16px;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s;
    background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
  }

  .upload-area:hover {
    border-color: #3b82f6;
    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
  }

  .upload-content .upload-icon {
    font-size: 48px;
    display: block;
    margin-bottom: 12px;
  }

  .upload-content p {
    margin: 4px 0;
    color: #374151;
    font-weight: 500;
  }

  .upload-hint {
    font-size: 12px;
    color: #9ca3af !important;
  }

  /* 数据源列表 */
  .data-sources-list {
    margin-top: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .data-source-item {
    display: flex;
    align-items: center;
    padding: 12px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .data-source-item:hover {
    border-color: #3b82f6;
    background: #eff6ff;
    transform: translateX(2px);
  }

  .data-source-item.active {
    border-color: #3b82f6;
    background: #dbeafe;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }

  .source-icon {
    font-size: 20px;
    margin-right: 12px;
  }

  .source-info {
    flex: 1;
    min-width: 0;
  }

  .source-name {
    font-weight: 600;
    color: #1f2937;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .source-rows {
    font-size: 12px;
    color: #6b7280;
  }

  .remove-btn {
    background: none;
    border: none;
    color: #ef4444;
    cursor: pointer;
    padding: 4px;
    font-size: 16px;
    opacity: 0.6;
    transition: all 0.2s;
    border-radius: 4px;
  }

  .remove-btn:hover {
    opacity: 1;
    background: #fee2e2;
  }

  /* 图表类型网格 */
  .chart-type-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }

  .chart-type-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 12px 8px;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    background: white;
  }

  .chart-type-card:hover {
    border-color: #3b82f6;
    background: #eff6ff;
    transform: translateY(-2px);
  }

  .chart-type-card.active {
    border-color: #3b82f6;
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    color: white;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
  }

  .chart-type-icon {
    font-size: 24px;
    margin-bottom: 4px;
  }

  .chart-type-name {
    font-size: 11px;
    font-weight: 500;
    text-align: center;
  }

  /* 字段配置 */
  .field-config {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .field-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .field-label {
    font-size: 13px;
    font-weight: 600;
    color: #374151;
  }

  .required {
    color: #ef4444;
    margin-left: 4px;
  }

  .optional {
    color: #9ca3af;
    font-size: 12px;
    margin-left: 4px;
  }

  .select-wrapper {
    position: relative;
  }

  .field-select {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 13px;
    background: white;
    cursor: pointer;
    transition: all 0.2s;
    appearance: none;
  }

  .field-select:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .field-select:hover {
    border-color: #9ca3af;
  }

  /* 样式配置 */
  .style-config {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .style-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .style-label {
    font-size: 13px;
    font-weight: 600;
    color: #374151;
  }

  .style-input {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 14px;
    transition: all 0.2s;
  }

  .style-input:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .style-checkbox-label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }

  .style-checkbox {
    width: 18px;
    height: 18px;
    border: 2px solid #d1d5db;
    border-radius: 4px;
    cursor: pointer;
  }

  .style-checkbox:checked {
    background: #3b82f6;
    border-color: #3b82f6;
  }

  .style-range {
    width: 100%;
    height: 6px;
    border-radius: 3px;
    background: #e5e7eb;
    outline: none;
  }

  .range-value {
    font-size: 12px;
    color: #6b7280;
    align-self: flex-end;
  }

  .color-picker-wrapper {
    width: 100%;
    height: 36px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    overflow: hidden;
    cursor: pointer;
  }

  .color-picker {
    width: 100%;
    height: 100%;
    border: none;
    cursor: pointer;
  }

  .color-palette {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 8px;
  }

  .color-swatch {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s;
    border: 2px solid transparent;
  }

  .color-swatch:hover {
    transform: scale(1.15);
  }

  .color-swatch.active {
    border-color: #1f2937;
    box-shadow:
      0 0 0 2px white,
      0 0 0 4px #3b82f6;
  }

  /* 系列配置 */
  .series-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .series-item {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    overflow: hidden;
    transition: all 0.2s;
  }

  .series-item:hover {
    border-color: #3b82f6;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
  }

  .series-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px;
    background: white;
    border-bottom: 1px solid #e5e7eb;
  }

  .series-name-input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    background: white;
  }

  .series-name-input:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .remove-series-btn {
    background: none;
    border: none;
    color: #ef4444;
    cursor: pointer;
    padding: 4px 8px;
    font-size: 14px;
    border-radius: 4px;
    transition: all 0.2s;
  }

  .remove-series-btn:hover {
    background: #fee2e2;
    transform: scale(1.1);
  }

  .series-fields {
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .series-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .series-fields .field-group .field-select {
    font-size: 12px;
    padding: 8px 10px;
  }

  .btn-add-series {
    width: 100%;
    padding: 12px;
    background: linear-gradient(135deg, #10b981, #059669);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .btn-add-series:hover {
    background: linear-gradient(135deg, #059669, #047857);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
  }

  /* 图表展示区 */
  .chart-display-area {
    flex: 1;
    position: relative;
    background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
    overflow: hidden;
  }

  .chart-wrapper {
    border: 2px solid #e5e7eb;
    border-radius: 12px;
    background: white;
    transition: all 0.3s;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  }

  .chart-wrapper:hover {
    box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
  }

  .chart-wrapper.active {
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .chart-dom {
    width: 100%;
    height: 100%;
  }

  .chart-actions {
    position: absolute;
    top: 8px;
    right: 8px;
    display: flex;
    gap: 4px;
    z-index: 20;
  }

  .action-btn {
    width: 32px;
    height: 32px;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    background: white;
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  }

  .action-btn:hover {
    background: #f9fafb;
    border-color: #3b82f6;
    transform: translateY(-1px);
  }

  .action-btn.active {
    background: #3b82f6;
    color: white;
    border-color: #3b82f6;
  }

  .action-btn.delete-btn:hover {
    background: #fee2e2;
    border-color: #ef4444;
    color: #ef4444;
  }

  .drag-handle {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 32px;
    background: transparent;
    cursor: move;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .drag-icon {
    color: #d1d5db;
    font-weight: bold;
    opacity: 0;
    transition: opacity 0.2s;
  }

  .chart-wrapper:hover .drag-icon {
    opacity: 0.5;
  }

  .resize-handle {
    position: absolute;
    bottom: 0;
    right: 0;
    width: 20px;
    height: 20px;
    background: linear-gradient(135deg, transparent 50%, #3b82f6 50%);
    cursor: nwse-resize;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .resize-icon {
    color: white;
    font-size: 12px;
  }

  /* 空状态 */
  .empty-state {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
    color: #9ca3af;
  }

  .empty-icon {
    font-size: 80px;
    margin-bottom: 20px;
    opacity: 0.6;
  }

  .empty-title {
    font-size: 20px;
    font-weight: 600;
    color: #6b7280;
    margin-bottom: 8px;
  }

  .empty-hint {
    font-size: 14px;
    color: #9ca3af;
    margin-bottom: 20px;
  }

  .empty-action-btn {
    padding: 12px 24px;
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .empty-action-btn:hover {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
  }

  /* 底部操作栏 */
  .editor-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding: 16px 24px;
    border-top: 1px solid #e5e7eb;
    background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
  }

  .footer-left,
  .footer-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .btn {
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .btn-primary {
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    color: white;
    box-shadow: 0 2px 4px rgba(59, 130, 246, 0.2);
  }

  .btn-primary:hover {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(59, 130, 246, 0.3);
  }

  .btn-secondary {
    background: white;
    border: 1px solid #d1d5db;
    color: #374151;
  }

  .btn-secondary:hover {
    background: #f3f4f6;
    border-color: #9ca3af;
  }

  .btn-export {
    background: linear-gradient(135deg, #8b5cf6, #7c3aed);
    color: white;
    box-shadow: 0 2px 4px rgba(139, 92, 246, 0.2);
  }

  .btn-export:hover {
    background: linear-gradient(135deg, #7c3aed, #6d28d9);
    transform: translateY(-1px);
  }

  .btn-close {
    background: #ef4444;
    color: white;
  }

  .btn-close:hover {
    background: #dc2626;
  }

  /* 导出菜单 */
  .export-group {
    position: relative;
  }

  .export-menu {
    position: absolute;
    bottom: calc(100% + 12px);
    right: 0;
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
    padding: 8px;
    min-width: 220px;
    z-index: 100;
  }

  .export-option {
    width: 100%;
    padding: 10px 14px;
    border: none;
    background: none;
    text-align: left;
    cursor: pointer;
    font-size: 14px;
    color: #374151;
    border-radius: 6px;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .export-option:hover {
    background: #f3f4f6;
  }

  .option-icon {
    font-size: 16px;
  }

  /* 帮助弹窗 */
  .help-modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    backdrop-filter: blur(4px);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 10000;
  }

  .help-content {
    background: white;
    border-radius: 16px;
    width: 90%;
    max-width: 600px;
    max-height: 80vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .help-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    border-bottom: 1px solid #e5e7eb;
    background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
  }

  .help-header h3 {
    margin: 0;
    font-size: 18px;
    font-weight: 700;
    color: #1f2937;
  }

  .help-body {
    padding: 24px;
    overflow-y: auto;
    flex: 1;
  }

  .help-section {
    margin-bottom: 24px;
  }

  .help-section h4 {
    margin: 0 0 12px 0;
    font-size: 15px;
    font-weight: 600;
    color: #1f2937;
  }

  .help-section p {
    margin: 0 0 12px 0;
    color: #6b7280;
    line-height: 1.6;
  }

  .help-section ul {
    margin: 0;
    padding-left: 20px;
    color: #6b7280;
  }

  .help-section li {
    margin-bottom: 6px;
    line-height: 1.6;
  }

  /* 标记点配置样式 */
  .mark-points-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 12px;
  }

  .mark-point-item {
    position: relative;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px;
  }

  .mark-point-item:hover {
    border-color: #3b82f6;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
  }

  .mark-point-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 10px;
  }

  .mark-point-row:last-of-type {
    margin-bottom: 0;
  }

  .mark-label {
    font-size: 12px;
    font-weight: 600;
    color: #374151;
  }

  .mark-input {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 13px;
    background: white;
    transition: all 0.2s;
  }

  .mark-input:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  .mark-remove-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    background: none;
    border: none;
    color: #ef4444;
    cursor: pointer;
    padding: 4px;
    font-size: 14px;
    opacity: 0.6;
    transition: all 0.2s;
    border-radius: 4px;
  }

  .mark-remove-btn:hover {
    opacity: 1;
    background: #fee2e2;
  }

  .btn-add-mark {
    width: 100%;
    margin-top: 12px;
    padding: 10px;
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }

  .btn-add-mark:hover {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    transform: translateY(-1px);
    box-shadow: 0 3px 8px rgba(59, 130, 246, 0.3);
  }

  /* 趋势线配置样式 */
  .trend-info {
    margin-top: 16px;
    padding: 12px;
    background: #eff6ff;
    border: 1px solid #dbeafe;
    border-radius: 8px;
  }

  .trend-stat {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
    font-size: 13px;
  }

  .trend-stat:last-child {
    padding-bottom: 0;
  }

  .trend-label {
    font-weight: 600;
    color: #1f2937;
  }

  .trend-value {
    font-family: monospace;
    color: #3b82f6;
    font-weight: 600;
  }

  /* 高级样式分隔线 */
  .style-divider {
    border-top: 1px solid #e5e7eb;
    padding-top: 16px;
    margin: 8px 0 16px 0;
    font-size: 13px;
    font-weight: 600;
    color: #6b7280;
  }

  /* 多坐标轴配置样式 */
  .series-axis-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 8px;
    max-height: 300px;
    overflow-y: auto;
  }

  .series-axis-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    transition: all 0.2s;
  }

  .series-axis-item:hover {
    border-color: #3b82f6;
    background: #eff6ff;
  }

  .axis-series-name {
    font-size: 13px;
    font-weight: 600;
    color: #374151;
    flex: 1;
  }

  .axis-selector {
    display: flex;
    gap: 12px;
  }

  .axis-option {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 500;
    color: #374151;
    cursor: pointer;
    padding: 6px 12px;
    border-radius: 6px;
    transition: all 0.2s;
    border: 1px solid #e5e7eb;
    background: white;
  }

  .axis-option:hover {
    border-color: #3b82f6;
    background: #eff6ff;
  }

  .axis-option input[type='radio'] {
    accent-color: #3b82f6;
  }

  .axis-label-left {
    color: #3b82f6;
  }

  .axis-label-right {
    color: #ef4444;
  }

  /* 滚动条样式 */
  .config-panel::-webkit-scrollbar,
  .help-body::-webkit-scrollbar,
  .series-axis-list::-webkit-scrollbar {
    width: 8px;
  }

  .config-panel::-webkit-scrollbar-track,
  .help-body::-webkit-scrollbar-track,
  .series-axis-list::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 4px;
  }

  .config-panel::-webkit-scrollbar-thumb,
  .help-body::-webkit-scrollbar-thumb,
  .series-axis-list::-webkit-scrollbar-thumb {
    background: #c1c1c1;
    border-radius: 4px;
  }

  /* 数据处理配置样式 */
  .radio-group {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .radio-option {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 500;
    color: #374151;
    cursor: pointer;
    padding: 8px 14px;
    border-radius: 6px;
    transition: all 0.2s;
    border: 1px solid #e5e7eb;
    background: white;
  }

  .radio-option:hover {
    border-color: #3b82f6;
    background: #eff6ff;
  }

  .radio-option input[type='radio'] {
    accent-color: #3b82f6;
  }

  .field-hint {
    font-size: 11px;
    color: #9ca3af;
    margin-top: 4px;
    display: block;
  }

  .data-preview-info {
    margin-top: 12px;
    padding: 12px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
  }

  .preview-stat {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 0;
    font-size: 13px;
  }

  .preview-stat:last-child {
    padding-bottom: 0;
  }

  .preview-label {
    font-weight: 600;
    color: #6b7280;
  }

  .preview-value {
    font-family: monospace;
    color: #3b82f6;
    font-weight: 600;
  }

  /* 模板管理样式 */
  .template-save-row {
    display: flex;
    gap: 8px;
  }

  .btn-save-template {
    padding: 10px 16px;
    background: linear-gradient(135deg, #10b981, #059669);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .btn-save-template:hover {
    background: linear-gradient(135deg, #059669, #047857);
    transform: translateY(-1px);
    box-shadow: 0 3px 8px rgba(16, 185, 129, 0.3);
  }

  .templates-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 12px;
  }

  .template-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    transition: all 0.2s;
  }

  .template-item:hover {
    border-color: #3b82f6;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
  }

  .template-item.active {
    border-color: #3b82f6;
    background: #eff6ff;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }

  .template-info {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    cursor: pointer;
  }

  .template-icon {
    font-size: 24px;
  }

  .template-details {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .template-name {
    font-weight: 600;
    font-size: 14px;
    color: #1f2937;
  }

  .template-meta {
    font-size: 11px;
    color: #6b7280;
  }

  .template-actions {
    display: flex;
    gap: 4px;
  }

  .template-action-btn {
    width: 32px;
    height: 32px;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    background: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    font-size: 14px;
  }

  .template-action-btn:hover {
    transform: scale(1.1);
  }

  .template-action-btn.apply-btn:hover {
    background: #d1fae5;
    border-color: #10b981;
  }

  .template-action-btn.delete-btn:hover {
    background: #fee2e2;
    border-color: #ef4444;
  }

  .empty-templates {
    text-align: center;
    padding: 32px 16px;
    color: #9ca3af;
  }

  .empty-templates .empty-icon {
    font-size: 48px;
    display: block;
    margin-bottom: 12px;
    opacity: 0.6;
  }

  .empty-templates p {
    margin: 4px 0;
    font-size: 14px;
  }

  .empty-templates .empty-hint {
    font-size: 12px;
    color: #6b7280;
  }

  .template-batch-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }

  .btn-batch {
    flex: 1;
    min-width: 120px;
    padding: 10px 14px;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    color: #374151;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }

  .btn-batch:hover {
    background: #f3f4f6;
    border-color: #9ca3af;
    transform: translateY(-1px);
  }

  .btn-batch-danger {
    color: #ef4444;
    border-color: #fca5a5;
  }

  .btn-batch-danger:hover {
    background: #fee2e2;
    border-color: #ef4444;
  }

  /* 主题系统样式 */
  .theme-presets-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }

  .theme-preset-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 12px;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.2s;
    background: white;
  }

  .theme-preset-card:hover {
    border-color: #3b82f6;
    background: #eff6ff;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
  }

  .theme-preset-card.active {
    border-color: #3b82f6;
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    color: white;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }

  .theme-preset-icon {
    font-size: 24px;
    margin-bottom: 4px;
  }

  .theme-preset-name {
    font-size: 13px;
    font-weight: 600;
    color: inherit;
  }

  .theme-preset-colors {
    display: flex;
    gap: 4px;
    margin-top: 6px;
  }

  .theme-color-dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 2px solid rgba(0, 0, 0, 0.1);
  }

  .custom-theme-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: 12px;
  }

  .color-input-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .color-picker-large {
    width: 48px;
    height: 36px;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    cursor: pointer;
    padding: 0;
  }

  .color-picker-large::-webkit-color-swatch-wrapper {
    padding: 2px;
  }

  .color-picker-large::-webkit-color-swatch {
    border: none;
    border-radius: 4px;
  }

  .color-hex-input {
    flex: 1;
    font-family: monospace;
    text-transform: uppercase;
  }

  .theme-preview-box {
    padding: 16px;
    border: 2px solid #e5e7eb;
    border-radius: 12px;
    margin-top: 12px;
    transition: all 0.3s;
  }

  .theme-preview-chart {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .theme-preview-title {
    font-size: 14px;
    font-weight: 600;
    text-align: center;
  }

  .theme-preview-content {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .theme-preview-bar {
    height: 8px;
    border-radius: 4px;
    background: v-bind(
      'currentTheme === "custom" ? customTheme.primaryColor : (themePresets.find(t => t.id === currentTheme.value)?.colors?.primaryColor || "#3b82f6")'
    );
  }

  .theme-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 12px;
  }

  .btn-theme-action {
    flex: 1;
    min-width: 100px;
    padding: 10px 14px;
    background: white;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    color: #374151;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }

  .btn-theme-action:hover {
    background: #f3f4f6;
    border-color: #9ca3af;
    transform: translateY(-1px);
  }

  /* 批量操作样式 */
  .batch-toggle-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }

  .btn-batch-apply {
    padding: 10px 16px;
    background: linear-gradient(135deg, #8b5cf6, #7c3aed);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .btn-batch-apply:hover {
    background: linear-gradient(135deg, #7c3aed, #6d28d9);
    transform: translateY(-1px);
    box-shadow: 0 3px 8px rgba(139, 92, 246, 0.3);
  }

  .batch-size-row {
    display: flex;
    gap: 12px;
    align-items: flex-end;
  }

  .batch-size-group {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 0 0 auto;
  }

  .batch-size-label {
    font-size: 12px;
    font-weight: 600;
    color: #6b7280;
    white-space: nowrap;
  }

  .size-input {
    width: 80px;
    padding: 8px 10px;
    font-size: 13px;
  }

  .batch-size-unit {
    font-size: 12px;
    color: #9ca3af;
    width: 24px;
  }

  .batch-grid-options {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }

  .batch-grid-btn {
    padding: 12px 16px;
    background: white;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    color: #374151;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .batch-grid-btn:hover {
    border-color: #3b82f6;
    background: #eff6ff;
    transform: translateY(-2px);
  }

  .batch-grid-btn.active {
    border-color: #3b82f6;
    background: linear-gradient(135deg, #3b82f6, #2563eb);
    color: white;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }

  .batch-export-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 12px;
  }

  .btn-batch-export {
    flex: 1;
    min-width: 150px;
    padding: 12px 16px;
    background: linear-gradient(135deg, #10b981, #059669);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }

  .btn-batch-export:hover {
    background: linear-gradient(135deg, #059669, #047857);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
  }

  /* 智能推荐样式 */
  .btn-analyze {
    width: 100%;
    padding: 12px 16px;
    background: linear-gradient(135deg, #f59e0b, #d97706);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .btn-analyze:hover {
    background: linear-gradient(135deg, #d97706, #b45309);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
  }

  .recommendations-container {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-top: 16px;
  }

  .analysis-result {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    padding: 12px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
  }

  .analysis-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px;
    background: white;
    border-radius: 6px;
    border: 1px solid #e5e7eb;
  }

  .analysis-label {
    font-size: 11px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
  }

  .analysis-value {
    font-size: 13px;
    font-weight: 600;
    color: #1f2937;
    font-family: monospace;
  }

  .analysis-value.good {
    color: #10b981;
  }

  .analysis-value.medium {
    color: #f59e0b;
  }

  .analysis-value.poor {
    color: #ef4444;
  }

  .recommendations-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .recommendation-card {
    padding: 14px;
    background: white;
    border: 2px solid #e5e7eb;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .recommendation-card:hover {
    border-color: #f59e0b;
    background: #fffbeb;
    transform: translateX(4px);
    box-shadow: 0 4px 12px rgba(245, 158, 11, 0.15);
  }

  .rec-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
  }

  .rec-icon {
    font-size: 28px;
  }

  .rec-title-group {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
  }

  .rec-title {
    font-size: 15px;
    font-weight: 700;
    color: #1f2937;
  }

  .rec-score {
    font-size: 12px;
    font-weight: 600;
    color: #f59e0b;
  }

  .rec-priority {
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .rec-priority.priority-high {
    background: #dcfce7;
    color: #16a34a;
  }

  .rec-priority.priority-medium {
    background: #fef3c7;
    color: #d97706;
  }

  .rec-priority.priority-low {
    background: #f3f4f6;
    color: #6b7280;
  }

  .rec-reason {
    margin: 0;
    padding: 0;
    font-size: 13px;
    color: #6b7280;
    line-height: 1.5;
    margin-bottom: 10px;
  }

  .rec-config {
    padding: 10px;
    background: #f9fafb;
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .rec-config-title {
    font-size: 11px;
    font-weight: 700;
    color: #6b7280;
    text-transform: uppercase;
  }

  .rec-config-items {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .rec-config-item {
    font-size: 12px;
    color: #4b5563;
  }

  .rec-config-item strong {
    color: #1f2937;
  }

  .btn-apply-top-rec {
    width: 100%;
    padding: 12px 16px;
    background: linear-gradient(135deg, #10b981, #059669);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin-top: 12px;
  }

  .btn-apply-top-rec:hover {
    background: linear-gradient(135deg, #059669, #047857);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
  }

  .smart-empty {
    text-align: center;
    padding: 32px 16px;
    color: #9ca3af;
  }

  .smart-empty .empty-icon {
    font-size: 48px;
    display: block;
    margin-bottom: 12px;
    opacity: 0.6;
  }

  .smart-empty p {
    margin: 4px 0;
    font-size: 14px;
  }

  .smart-empty .empty-hint {
    font-size: 12px;
    color: #6b7280;
  }

  .config-panel::-webkit-scrollbar-thumb:hover,
  .help-body::-webkit-scrollbar-thumb:hover,
  .series-axis-list::-webkit-scrollbar-thumb:hover {
    background: #a1a1a1;
  }
</style>
