<template>
  <div>
    <h2>掌握度报表</h2>
    <el-tabs v-model="tab">
      <el-tab-pane label="标注覆盖率" name="coverage">
        <div v-if="cov" class="stats">
          <el-row :gutter="12">
            <el-col :span="6"><el-card><div class="big">{{ cov.annotated_kp || 0 }}</div><div class="hint">已标注知识点</div></el-card></el-col>
            <el-col :span="6"><el-card><div class="big">{{ cov.total_kp || 0 }}</div><div class="hint">知识点总数</div></el-card></el-col>
            <el-col :span="6"><el-card><div class="big">{{ cov.coverage || '0%' }}</div><div class="hint">覆盖率</div></el-card></el-col>
            <el-col :span="6"><el-card><div class="big">{{ cov.mastery_users || 0 }}</div><div class="hint">已落地掌握度用户</div></el-card></el-col>
          </el-row>
          <h4 style="margin: 16px 0 8px">按学科拆分</h4>
          <el-table :data="cov.by_subject || []" border size="small">
            <el-table-column prop="subject" label="学科" width="100" />
            <el-table-column prop="annotated" label="已标注" width="120" />
            <el-table-column prop="total" label="总数" width="120" />
            <el-table-column prop="coverage" label="覆盖率" width="120" />
          </el-table>
        </div>
        <p v-else class="hint">（暂无数据）</p>
      </el-tab-pane>

      <el-tab-pane label="用户掌握度" name="user">
        <div class="toolbar" style="margin-bottom: 8px">
          <el-input v-model="userId" placeholder="输入 user_id" style="width: 200px" clearable @keyup.enter="loadUser" />
          <el-button type="primary" :loading="userLoading" @click="loadUser">查询</el-button>
        </div>
        <template v-if="userData">
          <el-row :gutter="12" style="margin-bottom: 12px">
            <el-col :span="6"><el-card><div class="big">{{ userData.overall?.total || 0 }}</div><div class="hint">知识点数</div></el-card></el-col>
            <el-col :span="6"><el-card><div class="big" style="color:#67c23a">{{ userData.overall?.mastered || 0 }}</div><div class="hint">已掌握</div></el-card></el-col>
            <el-col :span="6"><el-card><div class="big" style="color:#e6a23c">{{ userData.overall?.practicing || 0 }}</div><div class="hint">练习中</div></el-card></el-col>
            <el-col :span="6"><el-card><div class="big">{{ userData.overall?.rate || '0%' }}</div><div class="hint">掌握率</div></el-card></el-col>
          </el-row>
          <h4 style="margin: 16px 0 8px">按学科</h4>
          <el-table :data="userData.subjects || []" border size="small">
            <el-table-column prop="subject" label="学科" width="100" />
            <el-table-column prop="total" label="知识点数" width="120" />
            <el-table-column prop="mastered" label="已掌握" width="120" />
            <el-table-column prop="practicing" label="练习中" width="120" />
            <el-table-column prop="rate" label="掌握率" width="120" />
            <el-table-column label="明细" min-width="300" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="hint">{{ (row.items || []).slice(0, 3).map(x => x.title).join('、') }}{{ (row.items || []).length > 3 ? '…' : '' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
        <p v-else class="hint">（请输入 user_id 查询）</p>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const tab = ref('coverage')
const cov = ref(null)
const userId = ref('')
const userData = ref(null)
const userLoading = ref(false)

async function loadCov() {
  const { data: d } = await api.get('/api/admin/mastery/coverage')
  cov.value = d
}
async function loadUser() {
  if (!userId.value.trim()) { ElMessage.warning('请输入 user_id'); return }
  userLoading.value = true
  try {
    const { data: d } = await api.get(`/api/admin/mastery/users/${encodeURIComponent(userId.value.trim())}`)
    userData.value = d
  } catch (e) { ElMessage.error(e.response?.data?.message || e.message || '查询失败') }
  finally { userLoading.value = false }
}

onMounted(loadCov)
</script>

<style scoped>
.toolbar { display: flex; gap: 10px; align-items: center; }
.hint { color: #999; font-size: 12px; }
.stats .el-card { text-align: center; }
.big { font-size: 28px; font-weight: 700; color: #409eff; }
</style>
