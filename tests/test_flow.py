import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from database import ContinuityDB, DomainError

class ContinuityFlowTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=ContinuityDB(self.path)
        self.producer=self.db.add_user("制片","producer"); self.continuity=self.db.add_user("场记","continuity"); self.reviewer=self.db.add_user("审片","reviewer")
        self.production=self.db.create_production("测试影片","非线性拍摄",self.producer)
        self.scene=self.db.add_scene(self.production,"S01","雨夜",1)
        self.s1=self.db.add_shot(self.scene,"S01-01",2,1,"受伤后",self.continuity)
        self.s2=self.db.add_shot(self.scene,"S01-02",1,2,"受伤前",self.continuity)
        self.injury=self.db.add_element(self.production,"手臂伤痕","injury","monotonic","只能加重")
        self.db.set_element_state(self.s1,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.s2,self.injury,"轻度",1,"",self.continuity)
    def tearDown(self): self.db.close(); os.unlink(self.path)
    def test_conflict_plan_review_and_lock_flow(self):
        conflicts=self.db.check_scene(self.scene)
        self.assertEqual("regression",conflicts[0]["kind"])
        plan=self.db.propose_adjustment(conflicts[0]["id"],"重度",3,"将伤势调整到叙事顺序上的中间状态",self.continuity)
        result=self.db.review_adjustment(plan,True,self.reviewer,"通过")
        self.assertEqual([],result["conflicts"])
        self.db.lock_shot(self.s1,self.continuity); self.db.lock_shot(self.s2,self.continuity)
        with self.assertRaisesRegex(DomainError,"锁定"):
            self.db.set_element_state(self.s2,self.injury,"重度",3,"重做",self.continuity)
    def test_exemption_and_validation_failures(self):
        conflicts=self.db.check_scene(self.scene)
        with self.assertRaisesRegex(DomainError,"单调规则"):
            self.db.set_element_state(self.s1,self.injury,"未知",None,"",self.continuity)
        self.db.approve_exemption(conflicts[0]["id"],"闪回镜头中伤痕表现属于刻意叙事误差",self.reviewer)
        self.db.lock_shot(self.s1,self.continuity); self.db.lock_shot(self.s2,self.continuity)
        with self.assertRaisesRegex(DomainError,"只有审片人"):
            self.db.review_adjustment(999,True,self.continuity,"无权审核")

class CrossSceneFlowTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=ContinuityDB(self.path)
        self.producer=self.db.add_user("制片2","producer")
        self.continuity=self.db.add_user("场记2","continuity")
        self.reviewer=self.db.add_user("审片2","reviewer")
        self.production=self.db.create_production("跨场影片","",self.producer)
        self.sc1=self.db.add_scene(self.production,"S01","第一场",1)
        self.sc2=self.db.add_scene(self.production,"S02","第二场",2)
        # 叙事链：a(S01序1) -> b(S01序2) -> c(S02序1)
        self.a=self.db.add_shot(self.sc1,"S01-01",3,1,"",self.continuity)
        self.b=self.db.add_shot(self.sc1,"S01-02",2,2,"",self.continuity)
        self.c=self.db.add_shot(self.sc2,"S02-01",1,1,"",self.continuity)
        self.injury=self.db.add_element(self.production,"伤痕","injury","monotonic","")
        self.costume=self.db.add_element(self.production,"风衣","costume","stable","")

    def tearDown(self): self.db.close(); os.unlink(self.path)

    def test_inherited_state_does_not_overwrite_manual_values(self):
        # a=1，b 不写伤痕（沿用 a=1），c=2：沿用不产生冲突，人工值保留
        self.db.set_element_state(self.a,self.injury,"轻度",1,"",self.continuity)
        self.db.set_element_state(self.c,self.injury,"中度",2,"",self.continuity)
        conflicts=self.db.check_production(self.production)
        self.assertEqual([],conflicts)
        report=self.db.continuity_report(self.production)
        states={(s["id"],st["element_name"]):st for s in report["narrative_chain"] for st in s["states"]}
        self.assertEqual("inherited",states[(self.b,"伤痕")]["source"])
        self.assertEqual(1,states[(self.b,"伤痕")]["numeric_value"])
        self.assertEqual(self.a,states[(self.b,"伤痕")]["source_shot_id"])
        # 沿用只用于比较：element_states 中 b 仍无记录，a 的人工值未被动过
        self.assertIsNone(self.db.conn.execute(
            "SELECT numeric_value FROM element_states WHERE shot_id=? AND element_id=?",
            (self.b,self.injury)).fetchone())
        self.assertEqual(1,self.db.conn.execute(
            "SELECT numeric_value FROM element_states WHERE shot_id=? AND element_id=?",
            (self.a,self.injury)).fetchone()[0])

    def test_cross_scene_conflict_plan_and_lock(self):
        # 伤痕：a=3(同场 b 无记录，沿用 3)，c=1 -> 跨场次回退；风衣 a->c 状态变化 -> 跨场次
        self.db.set_element_state(self.a,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.c,self.injury,"轻度",1,"",self.continuity)
        self.db.set_element_state(self.a,self.costume,"整洁",None,"",self.continuity)
        self.db.set_element_state(self.c,self.costume,"沾泥",None,"",self.continuity)
        conflicts=self.db.check_production(self.production)
        kinds={c["kind"]:c for c in conflicts}
        for c in conflicts:
            self.assertTrue(c["cross_scene"])
            self.assertEqual(self.sc2,c["scene_id"])
            self.assertIn("跨场次",c["detail"])
        # 全片接口和跨场次筛选
        self.assertEqual(2,len(self.db.list_production_conflicts(self.production)))
        self.assertEqual(2,len(self.db.list_production_conflicts(self.production,cross_scene=True)))
        # 单场视图也能看到归属本场的跨场次冲突
        self.assertEqual({x["id"] for x in conflicts},{x["id"] for x in self.db.list_conflicts(self.sc2)})
        # 跨场次未处理冲突阻止锁定（from 端、to 端镜头都被阻止）
        with self.assertRaisesRegex(DomainError,"跨场次"):
            self.db.lock_shot(self.a,self.continuity)
        with self.assertRaisesRegex(DomainError,"跨场次"):
            self.db.lock_shot(self.c,self.continuity)
        # 豁免风衣冲突；伤痕冲突走调整方案复核，复核后报告与锁定结果一起更新
        self.db.approve_exemption(kinds["state_changed"]["id"],"跨场换装有剧情依据，必须保留",self.reviewer)
        plan=self.db.propose_adjustment(kinds["regression"]["id"],"重度",3,"按叙事链修正伤势",self.continuity)
        result=self.db.review_adjustment(plan,True,self.reviewer,"通过")
        remaining=result["production_conflicts"]
        self.assertEqual([kinds["state_changed"]["id"]],[c["id"] for c in remaining])
        self.assertEqual("exempted",remaining[0]["status"])
        # 伤痕冲突解决、风衣已豁免 -> 三个镜头全部可锁
        self.db.lock_shot(self.a,self.continuity); self.db.lock_shot(self.b,self.continuity); self.db.lock_shot(self.c,self.continuity)
        report=self.db.continuity_report(self.production)
        self.assertEqual(0,report["open_conflicts"]); self.assertEqual(1,report["exempted_conflicts"])

    def test_stale_conflicts_detach_when_shot_order_changes(self):
        self.db.set_element_state(self.a,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.b,self.injury,"轻度",1,"",self.continuity)
        old=self.db.check_production(self.production)[0]
        self.assertEqual((self.a,self.b),(old["from_shot_id"],old["to_shot_id"]))
        # 把 a 改到 b 之后：回退位置消失，旧冲突失效，不能继续挂在错误位置
        self.db.reorder_shot(self.a,3,self.continuity)
        gone=self.db.conn.execute("SELECT active,status FROM conflicts WHERE id=?",(old["id"],)).fetchone()
        self.assertEqual(0,gone["active"]); self.assertEqual("resolved",gone["status"])
        self.assertEqual([],self.db.list_production_conflicts(self.production))
        # 顺序改回来，同一问题重新出现（指纹复用记录）
        self.db.reorder_shot(self.a,1,self.continuity)
        again=self.db.list_production_conflicts(self.production)
        self.assertEqual(old["id"],again[0]["id"])
        self.assertEqual(1,again[0]["active"])
        # 针对失效冲突的待审方案不能再被批准
        cid=self.db.list_production_conflicts(self.production)[0]["id"]
        pid=self.db.propose_adjustment(cid,"轻度",1,"先提案",self.continuity)
        self.db.reorder_shot(self.a,3,self.continuity)  # 提案后冲突位置变化而失效
        with self.assertRaisesRegex(DomainError,"失效"):
            self.db.review_adjustment(pid,True,self.reviewer,"不能批准")

    def test_scene_reorder_moves_cross_scene_boundary(self):
        self.db.set_element_state(self.a,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.c,self.injury,"轻度",1,"",self.continuity)
        cross=[c for c in self.db.check_production(self.production) if c["cross_scene"]][0]
        self.assertEqual(self.sc2,cross["scene_id"])
        # S02 排到 S01 前面后，叙事链变为 c -> a -> b；c(1)->a(3) 不再回退，旧跨场冲突失效
        self.db.reorder_scene(self.sc2,1,self.producer)
        self.assertEqual(0,self.db.conn.execute("SELECT active FROM conflicts WHERE id=?",(cross["id"],)).fetchone()[0])
        self.assertEqual([],self.db.list_production_conflicts(self.production))

if __name__=="__main__": unittest.main()
