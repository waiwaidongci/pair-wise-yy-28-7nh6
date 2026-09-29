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

class FilmChainTest(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix=".db"); os.close(fd); self.db=ContinuityDB(self.path)
        self.producer=self.db.add_user("制片","producer"); self.continuity=self.db.add_user("场记","continuity"); self.reviewer=self.db.add_user("审片","reviewer")
        self.production=self.db.create_production("跨场影片","跨场次连续性",self.producer)
        self.scene1=self.db.add_scene(self.production,"S01","巷口",1)
        self.scene2=self.db.add_scene(self.production,"S02","安全屋",2)
        self.s1=self.db.add_shot(self.scene1,"S01-01",1,1,"开场",self.continuity)
        self.s2=self.db.add_shot(self.scene1,"S01-02",2,2,"追逐",self.continuity)
        self.s3=self.db.add_shot(self.scene2,"S02-01",3,1,"抵达",self.continuity)
        self.s4=self.db.add_shot(self.scene2,"S02-02",4,2,"收尾",self.continuity)
        self.jacket=self.db.add_element(self.production,"外套","costume","stable","颜色应一致")
        self.injury=self.db.add_element(self.production,"伤痕","injury","monotonic","只能加重")
    def tearDown(self): self.db.close(); os.unlink(self.path)
    def test_cross_scene_conflict_and_inheritance(self):
        self.db.set_element_state(self.s2,self.jacket,"蓝色",None,"",self.continuity)
        self.db.set_element_state(self.s3,self.jacket,"红色",None,"",self.continuity)
        conflicts=self.db.check_production(self.production)
        self.assertEqual(1,len(conflicts))
        self.assertEqual("state_changed",conflicts[0]["kind"])
        self.assertEqual(1,conflicts[0]["cross_scene"])
        self.assertEqual((self.s2,self.s3),(conflicts[0]["from_shot_id"],conflicts[0]["to_shot_id"]))
        report=self.db.continuity_report(self.production)
        chain={c["shot_id"]:c for c in report["film_chain"]}
        self.assertEqual([self.s1,self.s2,self.s3,self.s4],[c["shot_id"] for c in report["film_chain"]])
        s4_jacket=[s for s in chain[self.s4]["states"] if s["element_id"]==self.jacket][0]
        self.assertTrue(s4_jacket["inherited"]); self.assertEqual("红色",s4_jacket["state_value"]); self.assertEqual(self.s3,s4_jacket["source_shot_id"])
        s2_jacket=[s for s in chain[self.s2]["states"] if s["element_id"]==self.jacket][0]
        self.assertFalse(s2_jacket["inherited"])
        written=self.db.conn.execute("SELECT COUNT(*) FROM element_states WHERE shot_id=?",(self.s4,)).fetchone()[0]
        self.assertEqual(0,written,"沿用的状态不能写回镜头，人工写下的值不能被覆盖")
        self.assertEqual(1,report["cross_scene_open"])
    def test_cross_scene_plan_review_updates_report_and_lock(self):
        self.db.set_element_state(self.s2,self.jacket,"蓝色",None,"",self.continuity)
        self.db.set_element_state(self.s3,self.jacket,"红色",None,"",self.continuity)
        conflict=self.db.check_production(self.production)[0]
        plan=self.db.propose_adjustment(conflict["id"],"蓝色",None,"安全屋镜头应延续巷口的蓝色外套",self.continuity)
        result=self.db.review_adjustment(plan,True,self.reviewer,"通过")
        self.assertEqual([],result["conflicts"])
        report=self.db.continuity_report(self.production)
        self.assertEqual(0,report["open_conflicts"]); self.assertEqual(0,report["cross_scene_open"])
        for shot in (self.s1,self.s2,self.s3,self.s4): self.db.lock_shot(shot,self.continuity)
    def test_cross_scene_exemption_allows_lock(self):
        self.db.set_element_state(self.s2,self.jacket,"蓝色",None,"",self.continuity)
        self.db.set_element_state(self.s3,self.jacket,"红色",None,"",self.continuity)
        conflict=self.db.check_production(self.production)[0]
        with self.assertRaisesRegex(DomainError,"未处理冲突"):
            self.db.lock_shot(self.s3,self.continuity)
        self.db.approve_exemption(conflict["id"],"安全屋换装是剧情需要的刻意变化",self.reviewer)
        self.db.lock_shot(self.s3,self.continuity)
    def test_reorder_shot_moves_conflicts(self):
        self.db.set_element_state(self.s1,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.s2,self.injury,"轻度",1,"",self.continuity)
        conflicts=self.db.check_production(self.production)
        self.assertEqual(1,len(conflicts)); old_id=conflicts[0]["id"]
        self.db.reorder_shot(self.s2,1,self.continuity)
        remaining=self.db.check_production(self.production)
        self.assertEqual([],remaining,"换序后伤痕随叙事递增，旧冲突不能继续挂在错误位置")
        old=self.db.conn.execute("SELECT active,status FROM conflicts WHERE id=?",(old_id,)).fetchone()
        self.assertEqual((0,"resolved"),(old["active"],old["status"]))
        chain=[c["shot_id"] for c in self.db.continuity_report(self.production)["film_chain"]]
        self.assertEqual([self.s2,self.s1,self.s3,self.s4],chain)
    def test_reorder_scene_swaps_positions(self):
        self.db.set_element_state(self.s1,self.jacket,"蓝色",None,"",self.continuity)
        self.db.set_element_state(self.s3,self.jacket,"蓝色",None,"",self.continuity)
        self.assertEqual([],self.db.check_production(self.production))
        self.db.reorder_scene(self.scene2,1,self.continuity)
        chain=[(c["scene_number"],c["shot_code"]) for c in self.db.continuity_report(self.production)["film_chain"]]
        self.assertEqual([("S02","S02-01"),("S02","S02-02"),("S01","S01-01"),("S01","S01-02")],chain)
        self.assertEqual([],self.db.check_production(self.production))
    def test_scene_check_still_scoped_to_scene(self):
        self.db.set_element_state(self.s1,self.injury,"重度",3,"",self.continuity)
        self.db.set_element_state(self.s2,self.injury,"轻度",1,"",self.continuity)
        self.db.set_element_state(self.s2,self.jacket,"蓝色",None,"",self.continuity)
        self.db.set_element_state(self.s3,self.jacket,"红色",None,"",self.continuity)
        scene1_conflicts=self.db.check_scene(self.scene1)
        self.assertEqual(1,len(scene1_conflicts))
        self.assertEqual("regression",scene1_conflicts[0]["kind"])
        self.assertEqual(0,scene1_conflicts[0]["cross_scene"])
        scene2_conflicts=self.db.check_scene(self.scene2)
        self.assertEqual(1,len(scene2_conflicts))
        self.assertEqual("state_changed",scene2_conflicts[0]["kind"])
        self.assertEqual(1,scene2_conflicts[0]["cross_scene"])
        self.assertEqual(self.s3,scene2_conflicts[0]["to_shot_id"])

if __name__=="__main__": unittest.main()
